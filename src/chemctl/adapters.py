"""SSH sessions and read-only discovery. Never probe using qsub."""
from pathlib import Path
import re
import shlex
import time
import paramiko
from .credentials import load_key


def open_ssh(server, password=None):
    config = paramiko.SSHConfig()
    path = Path.home() / '.ssh' / 'config'
    if path.exists():
        with path.open() as source:
            config.parse(source)
    host = config.lookup(server['host'])
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    managed = load_key(server['managed_key_path']) if not password and server.get('managed_key_path') else None
    try:
        client.connect(hostname=host.get('hostname', server['host']),
                       port=server.get('port') or int(host.get('port', 22)),
                       username=server.get('username') or host.get('user'),
                       pkey=managed,
                       key_filename=None if password or managed else host.get('identityfile'), password=password,
                       allow_agent=not bool(password or managed), look_for_keys=not bool(password or managed),
                       timeout=15, banner_timeout=30, auth_timeout=60)
        client.get_transport().set_keepalive(30)
        return client
    except Exception:
        client.close()
        raise


def command(client, text, timeout=30, max_bytes=262144):
    channel = client.get_transport().open_session(timeout=10)
    channel.set_combine_stderr(True)
    try:
        channel.exec_command(text)
        channel.shutdown_write()
        chunks, size, deadline = [], 0, time.monotonic() + timeout
        while True:
            if channel.recv_ready():
                block = channel.recv(32768)
                size += len(block)
                if size > max_bytes:
                    raise RuntimeError('Remote command output exceeds the configured limit.')
                chunks.append(block)
            elif channel.exit_status_ready():
                return channel.recv_exit_status(), b''.join(chunks).decode(errors='replace')
            elif time.monotonic() >= deadline:
                raise TimeoutError('Remote command did not finish within its time limit.')
            else:
                time.sleep(0.03)
    finally:
        channel.close()


def discover_software(client):
    script = '''printf '=== PATH ===\\n'
for tool in orca g16 g09 g03; do command -v "$tool" || true; done
printf '=== environment ===\\n'
printf 'g16root=%s\\ng09root=%s\\nGAUSS_EXEDIR=%s\\n' "$g16root" "$g09root" "$GAUSS_EXEDIR"
printf '=== modules ===\\n'
if type module >/dev/null 2>&1; then module -t avail 2>&1 | grep -Ei 'orca|gaussian|g16|g09' || true; fi
printf '=== software locations ===\\n'
for base in /opt /usr/local /data/opt/local /public/software /apps /software "$HOME/software" "$HOME/apps"; do
  if [ -d "$base" ]; then find "$base" -maxdepth 5 \\( -name orca -o -name g16 -o -name g09 -o -name g16.profile -o -name g09.profile \\) -print 2>/dev/null; fi
done
true'''
    code, evidence = command(client, 'bash -lc ' + shlex.quote(script), timeout=45)
    return {'exit_code': code, 'evidence': evidence}


def probe_ssh(server, password=None, client=None):
    owned = client is None
    client = client or open_ssh(server, password)
    try:
        _, basic = command(client, 'uname -s; pwd; for tool in sbatch qsub bsub; do command -v "$tool" || true; done')
        lines = basic.splitlines()
        _, evidence = command(client,
            "printf '=== tools ===\\n'; "
            'for tool in qstat pbsnodes qconf; do command -v "$tool" || true; done; '
            "printf '=== qstat version ===\\n'; qstat --version 2>&1; "
            "printf '=== server ===\\n'; qstat -Bf 2>&1; "
            "printf '=== queues ===\\n'; qstat -Qf 2>&1; true")
        low = evidence.lower()
        detected = 'pbs' if 'pbs_version' in low or 'torque' in low or ('pbsnodes' in low and 'server:' in low) else 'unknown'
        if 'grid engine' in low or 'uge ' in low or 'sge ' in low:
            detected = 'sge'
        legacy = {}
        previous = server.get('last_probe', {}).get('scheduler_evidence', '')
        old_id = re.search(r'=== qsub help ===\s*(\d+\.[A-Za-z0-9_.-]+)', previous)
        if old_id:
            code, output = command(client, 'qstat -f ' + shlex.quote(old_id[1]))
            legacy = {'job_id': old_id[1], 'query_exit_code': code, 'output': output}
        return {'connected': True, 'system': lines[0] if lines else None,
                'login_directory': lines[1] if len(lines) > 1 else None,
                'scheduler_commands': lines[2:], 'scheduler': server['scheduler'],
                'detected_scheduler': detected, 'scheduler_evidence': evidence,
                'legacy_probe_job': legacy, 'session_active': True,
                'submission_supported': False}
    finally:
        if owned:
            client.close()
