import hashlib
import os
import shutil
import threading
import shlex
import paramiko
from pathlib import Path

from platformdirs import user_data_path

from . import __version__
from .adapters import open_ssh, probe_ssh, command, discover_software
from .credentials import save_key, load_key
from .parsing import PARSER_VERSION, fingerprint, parse_output
from .store import Store, now, uid
from .errors import ServiceError
from .remote_jobs import RemoteJobs


def default_home():
    return Path(os.environ["CHEMCTL_HOME"]) if "CHEMCTL_HOME" in os.environ else user_data_path("chemctl", appauthor=False)


def stable_id(prefix, value):
    return prefix + "_" + hashlib.sha256(value.encode()).hexdigest()[:20]


class Service:
    def __init__(self, home=None):
        self.home = Path(home) if home else default_home()
        self.store = Store(self.home)
        self.lock = threading.RLock()
        self.sessions = {}
        self.remote = RemoteJobs(self)
        self.monitor_stop = threading.Event()
        self.monitor_thread = None
        for job in self.store.list("job", 10000, filters={"simulated": False})["items"]:
            changed = False
            if job["status"] == "submitting":
                job.update(status="submission_unknown", message="API restarted during submission; refresh to recover the remote receipt. Do not resubmit.")
                changed = True
            elif job["status"] == "uploading":
                job.update(status="failed", message="API restarted during upload. No qsub was sent; preserve this partial directory and create a new request.")
                changed = True
            if job.get("sync_status") in ("queued", "running"):
                job.update(sync_status="failed", sync_error="API restarted during synchronization; sync again to resume.")
                changed = True
            if changed:
                self.store.put("job", job["job_id"], job)
        if not self.store.get("server", "demo"):
            self.store.put("server", "demo", {"server_id": "demo", "name": "Local simulation (no compute)", "adapter": "mock", "scheduler": "mock", "host": None, "remote_root": None})
        # A restart must not leave an interrupted batch looking active forever.
        for state in ("queued", "running"):
            for batch in self.store.list("batch", 10000, filters={"status": state})["items"]:
                batch.update(status="failed", error="Service restarted during this batch; submit the source again.")
                self.store.put("batch", batch["parse_batch_id"], batch)

    def require(self, kind, key):
        value = self.store.get(kind, key)
        if value is None:
            raise ServiceError("NOT_FOUND", f"{kind} {key} was not found", 404)
        return value

    def health(self):
        with self.store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"api": "ok", "database": "ok", "version": __version__, "parser_version": PARSER_VERSION,
                "home": str(self.home), "config_valid": True, "remote_availability": "not_checked",
                "capabilities": ["local_index", "cclib_parse", "json_cli", "desktop_gui", "mock_jobs", "ssh_probe", "pbs_jobs", "sftp_sync", "job_monitor"]}

    def server_save(self, data):
        if data["server_id"] == "demo":
            raise ServiceError("RESERVED_ID", "The demo server is reserved for simulation.")
        saved = self.store.get("server", data["server_id"]) or {}
        if all(saved.get(field) == data.get(field) for field in ("host", "username", "port")):
            for field in ("managed_key_path", "key_fingerprint", "key_enabled_at"):
                if field in saved:
                    data[field] = saved[field]
        previous = self.sessions.pop(data["server_id"], None)
        if previous:
            previous.close()
        self.store.put("server", data["server_id"], data)
        self.store.audit("server.configure", data["server_id"])
        return data

    def server_test(self, key, password=None):
        server = self.require("server", key)
        if server["adapter"] == "mock":
            return {"connected": True, "simulated": True, "message": "Local mock; no server connection or computation."}
        try:
            client = open_ssh(server, password)
            try:
                result = probe_ssh(server, client=client)
            except Exception:
                client.close()
                raise
            previous = self.sessions.pop(key, None)
            if previous:
                previous.close()
            self.sessions[key] = client
        except paramiko.AuthenticationException as exc:
            if "timeout" in str(exc).lower():
                raise ServiceError("SSH_AUTH_TIMEOUT", "SSH authentication received no reply within 60 seconds. This does not establish that the password is incorrect. Check whether AnySCP requires an additional login step.", 504) from exc
            raise ServiceError("SSH_AUTH_REJECTED", "The server rejected SSH authentication. Check the login credentials or whether an additional authentication step is required.", 401) from exc
        except Exception as exc:
            raise ServiceError("REMOTE_CONNECTION_FAILED", str(exc), 502) from exc
        self.store.audit("server.test", key, result)
        server["last_probe"] = {**result, "checked_at": now()}
        if result.get("detected_scheduler") == "pbs":
            server["scheduler"] = "pbs"
            result["submission_supported"] = True
            server["last_probe"]["submission_supported"] = True
        self.store.put("server", key, server)
        return result

    def server_software(self, key):
        with self.remote.lock:
            result = discover_software(self.remote.client(key))
        server = self.require("server", key)
        server["software_probe"] = {**result, "checked_at": now()}
        self.store.put("server", key, server)
        return result

    def server_enable_key(self, key):
        with self.remote.lock:
            server = self.require("server", key)
            client = self.remote.client(key)
            # A generated file is retained on a failed installation so retries reuse the same public key.
            identity = '|'.join(str(server.get(k)) for k in ('host', 'port', 'username'))
            path = self.home / 'keys' / (stable_id('ssh', identity) + '.dpapi')
            if path.exists():
                private = load_key(path)
            else:
                private = paramiko.RSAKey.generate(3072)
                save_key(path, private)
            public = private.get_name() + ' ' + private.get_base64()
            line = public + ' chemctl-managed'
            script = 'umask 077; mkdir -p "$HOME/.ssh" && touch "$HOME/.ssh/authorized_keys" && ' + \
                '(grep -qF -- ' + shlex.quote(public) + ' "$HOME/.ssh/authorized_keys" || printf \'\\n%s\\n\' ' + \
                shlex.quote(line) + ' >> "$HOME/.ssh/authorized_keys") && chmod 700 "$HOME/.ssh" && chmod 600 "$HOME/.ssh/authorized_keys"'
            code, output = command(client, script)
            if code:
                raise ServiceError('KEY_INSTALL_FAILED', output, 502)
            candidate = {**server, 'managed_key_path': str(path)}
            verified = open_ssh(candidate)
            verified.close()
            candidate.update(key_fingerprint=private.fingerprint, key_enabled_at=now())
            self.store.put('server', key, candidate)
            self.store.audit('server.key.enable', key, {'fingerprint': private.fingerprint})
            return {'enabled': True, 'fingerprint': private.fingerprint, 'storage': 'Windows DPAPI (current user)'}

    def close(self):
        self.monitor_stop.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        for client in self.sessions.values():
            client.close()
        self.sessions.clear()

    def start_monitor(self):
        def monitor():
            while not self.monitor_stop.wait(30):
                jobs = self.store.list("job", 200, filters={"simulated": False})["items"]
                for job in jobs:
                    if self.monitor_stop.is_set():
                        return
                    server = self.store.get("server", job["server_id"]) or {}
                    if job["status"] in ("queued", "running", "held", "unknown", "cancelling", "submission_unknown") and (job["server_id"] in self.sessions or server.get("managed_key_path")):
                        self.remote.refresh(job["job_id"])
        self.monitor_thread = threading.Thread(target=monitor, daemon=True, name="chemctl-monitor")
        self.monitor_thread.start()

    def scan(self, source, recursive=False):
        root = Path(source).expanduser().resolve()
        if not root.exists():
            raise ServiceError("PATH_NOT_FOUND", f"Path does not exist: {root}", 404)
        paths = [root] if root.is_file() else root.rglob("*") if recursive else root.glob("*")
        records = []
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in (".out", ".log"):
                continue
            stat = path.stat()
            key = stable_id("file", str(path))
            existing = self.store.get("file", key) or {}
            same = existing.get("size") == stat.st_size and existing.get("mtime_ns") == stat.st_mtime_ns
            if not same and existing.get("calculation_id"):
                calculation = self.require("calculation", existing["calculation_id"])
                calculation.update(status="not_parsed", calculation_status="stale", final_energy_eh=None)
                calculation["warnings"].append("Source changed since this calculation was parsed. Reparse before using its observations.")
                self.store.put("calculation", calculation["calculation_id"], calculation)
            row = {**existing, "file_id": key, "local_path": str(path), "filename": path.name,
                   "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "kind": "output",
                   "parse_status": existing.get("parse_status", "not_parsed") if same else "not_parsed",
                   "server_id": None, "scanned_at": now()}
            self.store.put("file", key, row)
            records.append(row)
        self.store.audit("file.scan", str(root), {"count": len(records)})
        return records

    def new_batch(self, source, recursive=True, force=False, idempotency_key=None, job_id=None):
        with self.lock:
            key = stable_id("batch", idempotency_key) if idempotency_key else uid("batch")
            previous = self.store.get("batch", key)
            if previous:
                if (previous["source"], previous["recursive"], previous["force"]) != (source, recursive, force):
                    raise ServiceError("IDEMPOTENCY_CONFLICT", "This key belongs to a different parse request.", 409)
                return previous, False
            if not Path(source).exists():
                raise ServiceError("PATH_NOT_FOUND", f"Path does not exist: {source}", 404)
            batch = {"parse_batch_id": key, "source": source, "recursive": recursive, "force": force,
                     "status": "queued", "total": 0, "processed": 0, "skipped": 0, "failed": 0,
                     "created_at": now(), "errors": [], "job_id": job_id}
            self.store.put("batch", key, batch)
            return batch, True

    def run_batch(self, key):
        # Serialize indexing to avoid two batches replacing the same calculation concurrently.
        with self.lock:
            batch = self.require("batch", key)
            batch["status"] = "running"
            self.store.put("batch", key, batch)
            try:
                files = self.scan(batch["source"], batch["recursive"])
                batch["total"] = len(files)
                for row in files:
                    try:
                        path = Path(row["local_path"])
                        digest = fingerprint(path)
                        if not batch["force"] and row.get("content_hash") == digest and row.get("parser_version") == PARSER_VERSION and row["parse_status"] in ("parsed", "partial", "unsupported"):
                            batch["skipped"] += 1
                        else:
                            result = parse_output(path)
                            end_stat = path.stat()
                            changed = (row["size"], row["mtime_ns"]) != (end_stat.st_size, end_stat.st_mtime_ns)
                            if changed:
                                result.update(status="partial", final_energy_eh=None, calculation_status="incomplete")
                                result["warnings"].append("File changed during indexing; cached fingerprint invalidated.")
                            calc_id = stable_id("calc", row["file_id"])
                            result.update(calculation_id=calc_id, file_id=row["file_id"], job_id=None,
                                          title=row["filename"], source_fingerprint=digest, parsed_at=now())
                            result["job_id"] = batch.get("job_id") or row.get("job_id")
                            self.store.put("calculation", calc_id, result)
                            row.update(parse_status=result["status"], calculation_id=calc_id,
                                       content_hash=None if changed else digest, parser_version=PARSER_VERSION,
                                       job_id=result["job_id"])
                            self.store.put("file", row["file_id"], row)
                            batch["processed"] += 1
                    except Exception as exc:
                        batch["failed"] += 1
                        batch["errors"].append({"file_id": row["file_id"], "message": str(exc)})
                        row["parse_status"] = "failed"
                        self.store.put("file", row["file_id"], row)
                        if row.get("calculation_id"):
                            old = self.require("calculation", row["calculation_id"])
                            old.update(status="failed", calculation_status="stale", final_energy_eh=None)
                            self.store.put("calculation", old["calculation_id"], old)
                    self.store.put("batch", key, batch)
                batch["status"] = "partially_succeeded" if batch["failed"] and batch["failed"] < batch["total"] else "failed" if batch["failed"] else "succeeded"
            except Exception as exc:
                batch.update(status="failed", error=str(exc))
            batch["finished_at"] = now()
            self.store.put("batch", key, batch)
            self.store.audit("parse.batch", key, {k: batch[k] for k in ("status", "processed", "skipped", "failed")})

    def calculations(self, limit=50, offset=0, engine=None, status=None, job_id=None, select=None):
        listing = self.store.list("calculation", limit, offset, {"engine": engine, "status": status, "job_id": job_id})
        fields = select.split(",") if select else ["calculation_id", "file_id", "title", "engine", "method", "basis_set", "solvent_name", "solvent_model", "status", "calculation_status", "final_energy_eh", "frequency_summary", "parsed_at"]
        listing["items"] = [{k: row.get(k) for k in fields} for row in listing["items"]]
        return listing

    def calculation_detail(self, key):
        row = self.require("calculation", key)
        # Older unsupported records predate these nullable summary fields.
        return {"calculation_status": None, "frequency_summary": None,
                **{k: v for k, v in row.items() if k not in ("energies", "structures", "frequencies")}}

    def submit(self, data):
        server = self.require("server", data["server_id"])
        if server["adapter"] != "mock":
            return self.remote.submit(data)
        source = Path(data["input_path"]).expanduser().resolve()
        if not source.exists():
            raise ServiceError("PATH_NOT_FOUND", f"Input not found: {source}", 404)
        paths = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file())
        if not paths:
            raise ServiceError("EMPTY_INPUT", "The input directory is empty.")
        manifest = [{"name": p.name if source.is_file() else p.relative_to(source).as_posix(), "size": p.stat().st_size, "sha256": fingerprint(p)} for p in paths]
        plan = {"server_id": data["server_id"], "engine": data["engine"], "profile": data["profile"],
                "tag": data["tag"], "input_path": str(source), "input_manifest": manifest,
                "simulated": server["adapter"] == "mock", "resources": None}
        if data["dry_run"]:
            return {**plan, "dry_run": True, "submission_supported": server["adapter"] == "mock"}
        if server["adapter"] != "mock":
            raise ServiceError("NOT_IMPLEMENTED", "Real submission requires a verified scheduler adapter and resource profile; only SSH probing is available in 0.1.", 501)
        with self.lock:
            key = stable_id("job", data["idempotency_key"])
            old = self.store.get("job", key)
            if old:
                if any(old.get(k) != v for k, v in plan.items()):
                    raise ServiceError("IDEMPOTENCY_CONFLICT", "This key belongs to different inputs or submission options.", 409)
                return old
            job = {**plan, "job_id": key, "remote_job_id": f"mock-{key}", "status": "queued",
                   "submitted_at": now(), "last_state_change_at": now(), "idempotency_key": data["idempotency_key"],
                   "message": "Simulation only. No files uploaded; no chemistry calculation executed."}
            self.store.put("job", key, job)
            self.store.audit("job.submit.mock", key)
            return job

    def cancel(self, key):
        if not self.require("job", key)["simulated"]:
            return self.remote.cancel(key)
        with self.lock:
            job = self.require("job", key)
            if job["status"] in ("completed", "failed", "cancelled"):
                raise ServiceError("INVALID_STATE", "Only active jobs can be cancelled.", 409)
            job.update(status="cancelled", last_state_change_at=now())
            self.store.put("job", key, job)
            self.store.audit("job.cancel.mock", key)
            return job

    def advance_mock(self, key):
        with self.lock:
            job = self.require("job", key)
            transitions = {"queued": "running", "running": "completed"}
            if not job["simulated"] or job["status"] not in transitions:
                raise ServiceError("INVALID_STATE", "Only queued/running mock jobs can advance.", 409)
            job.update(status=transitions[job["status"]], last_state_change_at=now())
            self.store.put("job", key, job)
            self.store.audit("job.advance.mock", key, {"status": job["status"]})
            return job

    def fetch(self, key, destination):
        row = self.require("file", key)
        target = Path(destination).expanduser().resolve()
        if target.is_dir():
            target /= row["filename"]
        # Exclusive creation prevents accidental replacement of user files.
        with Path(row["local_path"]).open("rb") as source, target.open("xb") as dest:
            shutil.copyfileobj(source, dest)
        self.store.audit("file.export", key, {"destination": str(target)})
        return {"path": str(target)}
