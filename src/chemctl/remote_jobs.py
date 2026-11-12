"""Torque/PBS jobs: explicit scripts, durable receipts, and bounded job directories."""
import hashlib
import json
import posixpath
import re
import shlex
import stat
import threading
import tempfile
from pathlib import Path, PurePosixPath

from .adapters import command, open_ssh
from .errors import ServiceError
from .parsing import fingerprint
from .store import now

JOB_ID = re.compile(r"^\d+(?:\.[A-Za-z0-9_.-]+)?$")


def pbs_state(output):
    fields = {}
    for line in output.splitlines():
        match = re.match(r"\s*([A-Za-z_][\w.]*)\s*=\s*(.*)", line)
        if match:
            fields[match[1]] = match[2].strip()
    raw = fields.get("job_state")
    exit_code = int(fields["exit_status"]) if re.fullmatch(r"-?\d+", fields.get("exit_status", "")) else None
    status = {"Q": "queued", "H": "held", "W": "queued", "T": "queued", "R": "running", "E": "running", "S": "held"}.get(raw, "unknown")
    if raw in ("C", "F") and exit_code is not None:
        status = "completed" if exit_code == 0 else "failed"
    return {"status": status, "scheduler_state": raw, "exit_code": exit_code,
            "resource_usage": {k: v for k, v in fields.items() if k.startswith("resources_used.")}}


def script_command(original, script_name):
    first = original.splitlines()[0] if original else ""
    args = shlex.split(first[2:]) if first.startswith("#!") else ["bash"]
    if args and posixpath.basename(args[0]) == "env":
        args = args[1:]
    if not args or posixpath.basename(args[0]) not in ("bash", "sh") or any(not re.fullmatch(r"-[eulx]+", flag) for flag in args[1:]):
        raise ServiceError("SCRIPT_SHELL", "Supported scripts use bash/sh with optional -e/-u/-l/-x flags. Other shebangs need an explicit bash wrapper.")
    return " ".join(shlex.quote(value) for value in [posixpath.basename(args[0]), *args[1:], "./" + script_name])


def wrapper_script(original, script_name, remote_directory):
    directives = "\n".join(line for line in original.splitlines() if line.lstrip().startswith("#PBS"))
    directory = shlex.quote(remote_directory)
    return (f"#!/bin/bash\n{directives}\n"
            f"cd {directory} || exit 111\n"
            "trap 'rc=$?; printf \"%s\\n\" \"$rc\" > .chemctl-exit.tmp; mv .chemctl-exit.tmp .chemctl-exit; exit \"$rc\"' EXIT\n"
            f"{script_command(original, script_name)}\n")


def server_identity(server):
    return {key: server.get(key) for key in ("host", "port", "username")}


def prepare_plan(server, data):
    probe = server.get("last_probe", {})
    if probe.get("detected_scheduler") != "pbs":
        raise ServiceError("SCHEDULER_UNCONFIRMED", "A PBS-family scheduler must be confirmed by a successful read-only probe.", 409)
    root = server.get("remote_root") or posixpath.join(probe.get("login_directory", ""), "chemctl-jobs")
    if not root.startswith("/") or root == "/" or ".." in PurePosixPath(root).parts:
        raise ServiceError("REMOTE_ROOT_REQUIRED", "Configure an absolute remote work directory below your home/project directory.")
    root = root.rstrip("/")
    source = Path(data["input_path"]).expanduser().resolve()
    if not source.exists():
        raise ServiceError("PATH_NOT_FOUND", f"Input not found: {source}", 404)
    base = source if source.is_dir() else source.parent
    script_name = data.get("script") or (source.name if source.is_file() and source.suffix.lower() in (".sh", ".pbs") else "")
    script = base / script_name
    if not script_name or PurePosixPath(script_name.replace("\\", "/")).is_absolute() or ".." in Path(script_name).parts or not script.is_file() or not script.resolve().is_relative_to(base):
        raise ServiceError("SCRIPT_REQUIRED", "Choose a PBS script inside the input directory using --script; no engine command or resources are guessed.")
    paths = sorted(p for p in base.rglob("*") if p.is_file()) if source.is_dir() else [source]
    manifest = []
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            raise ServiceError("INPUT_SYMLINK", f"Input symlinks outside the upload tree are not supported: {path}")
        name = path.relative_to(base).as_posix()
        if any(part.startswith(".chemctl-") for part in PurePosixPath(name).parts):
            raise ServiceError("RESERVED_FILENAME", f"Reserved input filename: {name}")
        manifest.append({"name": name, "size": path.stat().st_size, "sha256": fingerprint(path)})
    if script.resolve() not in [p.resolve() for p in paths]:
        raise ServiceError("SCRIPT_NOT_UPLOADED", "The selected script must be included in the submitted input.")
    original = script.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    script_command(original, script_name)
    key = "job_" + hashlib.sha256((data["server_id"] + ":" + data["idempotency_key"]).encode()).hexdigest()[:20]
    directory = root + "/" + key
    return {"job_id": key, "server_id": data["server_id"], "engine": data["engine"], "profile": data["profile"],
            "tag": data["tag"], "input_path": str(source), "input_manifest": manifest,
            "script": script.relative_to(base).as_posix(), "script_text": original,
            "wrapper_text": wrapper_script(original, script.relative_to(base).as_posix(), directory),
            "remote_root": root, "remote_directory": directory, "simulated": False,
            "resources": {"source": "user PBS script", "directives": [line for line in original.splitlines() if line.lstrip().startswith("#PBS")]},
            "submission_supported": True, "scheduler": "pbs", "server_identity": server_identity(server)}


def mkdirs(sftp, path):
    if path == "/":
        return
    try:
        info = sftp.lstat(path)
    except FileNotFoundError:
        mkdirs(sftp, posixpath.dirname(path))
        sftp.mkdir(path)
        return
    if not stat.S_ISDIR(info.st_mode):
        raise ServiceError("REMOTE_PATH_CONFLICT", f"Not a real directory: {path}", 409)


class RemoteJobs:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.lock = threading.RLock()

    def client(self, server_id, job=None):
        server = self.service.require("server", server_id)
        if job and job.get("server_identity") != server_identity(server):
            raise ServiceError("SERVER_IDENTITY_CHANGED", "This job belongs to the original host/account. Restore its connection configuration before operating on it.", 409)
        client = self.service.sessions.get(server_id)
        if not (client and client.get_transport() and client.get_transport().is_authenticated()):
            try:
                client = open_ssh(server)
            except Exception as exc:
                raise ServiceError("SSH_LOGIN_REQUIRED", "Reconnect in Servers → Check connection. The API keeps the authenticated connection in memory, not your password.", 409) from exc
            self.service.sessions[server_id] = client
        if job and job.get("connection_identity") != self.connection_identity(client):
            raise ServiceError("SERVER_IDENTITY_CHANGED", "The SSH peer/account differs from the submitted task's connection.", 409)
        return client

    @staticmethod
    def connection_identity(client):
        transport = client.get_transport()
        return {"peer": list(transport.getpeername()), "username": transport.get_username()}

    def submit(self, data):
        server = self.service.require("server", data["server_id"])
        plan = prepare_plan(server, data)
        plan["plan_hash"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        if data.get("expected_plan_hash") and data["expected_plan_hash"] != plan["plan_hash"]:
            raise ServiceError("PLAN_CHANGED", "Inputs or server configuration changed since preview. Generate a new dry-run plan.", 409)
        if data["dry_run"]:
            return {**plan, "dry_run": True}
        with self.lock:
            previous = self.store.get("job", plan["job_id"])
            if previous:
                if any(previous.get(k) != plan[k] for k in ("input_manifest", "script", "server_id", "remote_directory", "engine", "tag")):
                    raise ServiceError("IDEMPOTENCY_CONFLICT", "This key belongs to another input or submission plan.", 409)
                return previous  # An uncertain qsub receipt must never cause an automatic resubmission.
            client = self.client(data["server_id"])
            job = {**plan, "status": "uploading", "remote_job_id": None, "submitted_at": now(),
                   "last_state_change_at": now(), "idempotency_key": data["idempotency_key"],
                   "message": "Uploading explicit PBS script and inputs.", "sync_status": "not_synced",
                   "connection_identity": self.connection_identity(client)}
            self.store.put("job", job["job_id"], job)
            self.store.audit("job.submit.intent", job["job_id"], {"remote_directory": plan["remote_directory"]})
            try:
                with client.open_sftp() as sftp:
                    mkdirs(sftp, plan["remote_root"])
                    if sftp.normalize(plan["remote_root"]) != plan["remote_root"]:
                        raise ServiceError("REMOTE_PATH_SYMLINK", "Use the canonical remote root; symlink roots are not supported.")
                    try:
                        sftp.mkdir(plan["remote_directory"])
                    except OSError as exc:
                        raise ServiceError("REMOTE_PATH_CONFLICT", "The task directory already exists; it will not be overwritten.", 409) from exc
                    base = Path(plan["input_path"])
                    base = base if base.is_dir() else base.parent
                    for item in plan["input_manifest"]:
                        local = base / item["name"]
                        if fingerprint(local) != item["sha256"]:
                            raise ServiceError("INPUT_CHANGED", "An input changed after planning; create a new request.", 409)
                        remote = plan["remote_directory"] + "/" + item["name"]
                        mkdirs(sftp, posixpath.dirname(remote))
                        sftp.put(str(local), remote)
                    # Normalize shell line endings, preserving the previewed semantics.
                    with sftp.open(plan["remote_directory"] + "/" + plan["script"], "w") as out:
                        out.write(plan["script_text"])
                    with sftp.open(plan["remote_directory"] + "/.chemctl-run.sh", "w") as out:
                        out.write(plan["wrapper_text"])
                job.update(status="submitting", message="Submission sent once; a missing receipt requires reconciliation, not retry.")
                self.store.put("job", job["job_id"], job)
                name = "cc" + job["job_id"][-12:]
                directory = shlex.quote(plan["remote_directory"])
                # Save the qsub receipt remotely as well, so network interruption does not discard it.
                submit = (f"cd {directory} && qsub -S /bin/bash -N {name} -o {shlex.quote(plan['remote_directory'] + '/scheduler.stdout')} "
                          f"-e {shlex.quote(plan['remote_directory'] + '/scheduler.stderr')} ./.chemctl-run.sh "
                          "> .chemctl-receipt 2> .chemctl-submit-error; rc=$?; "
                          "cat .chemctl-receipt; cat .chemctl-submit-error >&2; exit $rc")
                code, receipt = command(client, submit, timeout=60)
                candidate = receipt.strip().splitlines()[0] if receipt.strip() else ""
                if code == 0 and JOB_ID.fullmatch(candidate):
                    job.update(status="queued", remote_job_id=candidate, message="Submitted to the real PBS scheduler.")
                else:
                    job.update(status="submission_unknown", message=f"qsub returned code {code}; inspect receipt before any resubmission.", submission_output=receipt)
            except Exception as exc:
                job.update(status="submission_unknown" if job["status"] == "submitting" else "failed", message=str(exc))
            job["last_state_change_at"] = now()
            self.store.put("job", job["job_id"], job)
            self.store.audit("job.submit.remote", job["job_id"], {"status": job["status"], "remote_job_id": job["remote_job_id"]})
            return job

    def refresh(self, key):
        with self.lock:
            job = self.service.require("job", key)
            if job["simulated"]:
                return job
            try:
                client = self.client(job["server_id"], job)
                with client.open_sftp() as sftp:
                    if job.get("status") == "submission_unknown" and not job.get("remote_job_id"):
                        try:
                            with sftp.open(job["remote_directory"] + "/.chemctl-receipt") as receipt:
                                remote_id = receipt.read(1024).decode().strip()
                            if JOB_ID.fullmatch(remote_id):
                                job["remote_job_id"] = remote_id
                        except FileNotFoundError:
                            pass
                    if not job.get("remote_job_id"):
                        return job
                    code, output = command(client, "qstat -f " + shlex.quote(job["remote_job_id"]))
                    old = job["status"]
                    if code == 0:
                        job.update(pbs_state(output))
                    elif "unknown job id" in output.lower():
                        job.update(status="unknown", scheduler_state="not_found")
                        try:
                            with sftp.open(job["remote_directory"] + "/.chemctl-exit") as marker:
                                exit_code = int(marker.read(64).decode().strip())
                            job.update(status="completed" if exit_code == 0 else "failed", exit_code=exit_code)
                        except FileNotFoundError:
                            if job.get("cancel_requested"):
                                job["status"] = "cancelled"
                    else:
                        raise RuntimeError(output.strip())
                    if job["status"] != old:
                        job["last_state_change_at"] = now()
                        self.store.audit("job.state.remote", key, {"from": old, "to": job["status"]})
                    job.update(last_polled_at=now(), last_poll_error=None, message="Status refreshed from PBS and the task exit record.")
            except Exception as exc:
                job.update(last_poll_attempt_at=now(), last_poll_error=str(exc))
            self.store.put("job", key, job)
            return job

    def cancel(self, key):
        with self.lock:
            job = self.service.require("job", key)
            if not job.get("remote_job_id") or job["status"] in ("completed", "failed", "cancelled"):
                raise ServiceError("INVALID_STATE", "Only known active remote tasks can be cancelled.", 409)
            code, output = command(self.client(job["server_id"], job), "qdel " + shlex.quote(job["remote_job_id"]))
            if code:
                raise ServiceError("CANCEL_FAILED", output.strip(), 502)
            job.update(status="cancelling", cancel_requested=True, last_state_change_at=now())
            self.store.put("job", key, job)
            self.store.audit("job.cancel.remote", key, {"remote_job_id": job["remote_job_id"]})
            return job

    def queue_sync(self, key):
        with self.lock:
            job = self.service.require("job", key)
            if job["simulated"]:
                raise ServiceError("MOCK_HAS_NO_OUTPUT", "Simulated jobs have no remote output.", 409)
            if job.get("sync_status") in ("queued", "running"):
                return job, False
            job.update(sync_status="queued", sync_error=None)
            self.store.put("job", key, job)
            return job, True

    def sync(self, key, parse=True):
        with self.lock:
            job = self.service.require("job", key)
            job.update(sync_status="running")
            self.store.put("job", key, job)
            cache = self.service.home / "cache" / key
            cache.mkdir(parents=True, exist_ok=True)
            previous = job.get("synced_files", {})
            copied, skipped, manifest = 0, 0, {}
            try:
                with self.client(job["server_id"], job).open_sftp() as sftp:
                    root = job["remote_directory"]
                    if sftp.normalize(root) != root:
                        raise ServiceError("REMOTE_PATH_SYMLINK", "Task directory changed to a symlink.")
                    pending = [(root, "")]
                    while pending:
                        directory, relative = pending.pop()
                        for entry in sftp.listdir_attr(directory):
                            name = entry.filename
                            if name in (".", "..") or "/" in name or "\\" in name or ":" in name:
                                raise ServiceError("INVALID_REMOTE_NAME", f"Unsupported filename: {name}")
                            if name.startswith(".chemctl-") or stat.S_ISLNK(entry.st_mode):
                                continue
                            rel = posixpath.join(relative, name)
                            remote = posixpath.join(directory, name)
                            if stat.S_ISDIR(entry.st_mode):
                                pending.append((remote, rel))
                            elif stat.S_ISREG(entry.st_mode):
                                target = cache / rel
                                if not target.resolve().is_relative_to(cache.resolve()):
                                    raise ServiceError("CACHE_PATH_ESCAPE", "Cache path escapes the task directory.")
                                stamp = {"size": entry.st_size, "mtime": entry.st_mtime}
                                if target.exists() and target.stat().st_size == entry.st_size and previous.get(rel) == stamp:
                                    skipped += 1
                                    manifest[rel] = stamp
                                    continue
                                target.parent.mkdir(parents=True, exist_ok=True)
                                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".chemctl-transfer-", delete=False) as temp:
                                    temporary = Path(temp.name)
                                sftp.get(remote, str(temporary))
                                after = sftp.stat(remote)
                                temporary.replace(target)
                                if (after.st_size, after.st_mtime) == (entry.st_size, entry.st_mtime):
                                    manifest[rel] = stamp
                                copied += 1
                job.update(sync_status="succeeded", synced_files=manifest, cache_path=str(cache), last_synced_at=now(),
                           sync_summary={"downloaded": copied, "unchanged": skipped})
                if parse:
                    batch, _ = self.service.new_batch(str(cache), recursive=True, job_id=key)
                    self.service.run_batch(batch["parse_batch_id"])
                    job["parse_batch_id"] = batch["parse_batch_id"]
            except Exception as exc:
                job.update(sync_status="failed", sync_error=str(exc))
            self.store.put("job", key, job)
            self.store.audit("job.sync.remote", key, {"status": job["sync_status"], "downloaded": copied, "unchanged": skipped})
