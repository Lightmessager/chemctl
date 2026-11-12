import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr
from starlette.exceptions import HTTPException

from .service import Service, ServiceError
from .store import now


def envelope(data=None, error=None):
    return {"ok": error is None, "data": data, "error": error, "meta": {"api_version": "1", "timestamp": now()}}


class SourceRequest(BaseModel):
    source: str
    recursive: bool = True
    force: bool = False
    idempotency_key: str | None = None


class JobRequest(BaseModel):
    server_id: str = "demo"
    input_path: str
    engine: Literal["orca", "gaussian09d"] = "orca"
    profile: str = "default"
    tag: str = ""
    dry_run: bool = False
    script: str | None = None
    expected_plan_hash: str | None = None
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ServerRequest(BaseModel):
    server_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    name: str
    host: str
    username: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    remote_root: str
    scheduler: Literal["slurm", "pbs", "sge", "lsf", "direct", "unknown"] = "unknown"
    adapter: Literal["ssh"] = "ssh"


class Destination(BaseModel):
    destination: str


class ProbeRequest(BaseModel):
    password: SecretStr | None = None


class SyncRequest(BaseModel):
    parse: bool = True


def create_app(home: Path | None = None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = Service(home)
        app.state.service.start_monitor()
        yield
        app.state.service.close()

    app = FastAPI(title="chemctl", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # No cookie auth or CORS. Reject cross-origin browser writes to this local filesystem API.
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            return JSONResponse(envelope(error={"code": "ORIGIN_DENIED", "message": "Use the desktop client or CLI."}), 403)
        if request.headers.get("host", "").split(":")[0] not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse(envelope(error={"code": "HOST_DENIED", "message": "Local API only."}), 403)
        return await call_next(request)

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(envelope(error={"code": exc.code, "message": str(exc)}), exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(envelope(error={"code": "VALIDATION_ERROR", "message": str(exc)}), 422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(envelope(error={"code": "HTTP_ERROR", "message": str(exc.detail)}), exc.status_code)

    @app.exception_handler(OSError)
    async def os_error(request, exc):
        return JSONResponse(envelope(error={"code": "FILESYSTEM_ERROR", "message": str(exc)}), 400)

    def service():
        return app.state.service

    @app.get("/api/v1/health")
    def health():
        return envelope(service().health())

    @app.get("/api/v1/servers")
    def servers(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return envelope(service().store.list("server", limit, offset))

    @app.post("/api/v1/servers/{key}/software")
    def software(key: str):
        return envelope(service().server_software(key))

    @app.post("/api/v1/servers/{key}/enable-key")
    def enable_key(key: str):
        return envelope(service().server_enable_key(key))

    @app.post("/api/v1/servers")
    def configure(body: ServerRequest):
        return envelope(service().server_save(body.model_dump()))

    @app.post("/api/v1/servers/{key}/test")
    def test_server(key: str, body: ProbeRequest | None = None):
        password = body.password.get_secret_value() if body and body.password else None
        return envelope(service().server_test(key, password))

    @app.get("/api/v1/jobs")
    def jobs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), status: str | None = None, server: str | None = None):
        return envelope(service().store.list("job", limit, offset, {"status": status, "server_id": server}))

    @app.post("/api/v1/jobs")
    def submit(body: JobRequest):
        return envelope(service().submit(body.model_dump()))

    @app.get("/api/v1/jobs/{key}")
    def job(key: str):
        return envelope(service().require("job", key))

    @app.post("/api/v1/jobs/{key}/cancel")
    def cancel(key: str):
        return envelope(service().cancel(key))

    @app.post("/api/v1/jobs/{key}/refresh")
    def refresh_job(key: str):
        return envelope(service().remote.refresh(key))

    @app.post("/api/v1/jobs/{key}/sync")
    def sync_job(key: str, background: BackgroundTasks, body: SyncRequest | None = None):
        job, created = service().remote.queue_sync(key)
        if created:
            background.add_task(service().remote.sync, key, body.parse if body else True)
        return envelope(job)

    @app.post("/api/v1/jobs/{key}/advance-mock")
    def advance(key: str):
        return envelope(service().advance_mock(key))

    @app.get("/api/v1/jobs/{key}/events")
    def events(key: str):
        service().require("job", key)
        return envelope(service().store.events(key))

    @app.get("/api/v1/jobs/{key}/diagnose")
    def diagnose(key: str):
        job = service().require("job", key)
        return envelope({"job_id": key, "status": job["status"], "simulated": job["simulated"], "message": job["message"], "events": service().store.events(key, 5)})

    @app.get("/api/v1/files")
    def files(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), status: str | None = None):
        return envelope(service().store.list("file", limit, offset, {"parse_status": status}))

    @app.post("/api/v1/files/scan")
    def scan(body: SourceRequest):
        records = service().scan(body.source, body.recursive)
        return envelope({"count": len(records), "message": "Use file list to page through indexed files."})

    @app.get("/api/v1/files/{key}")
    def file_info(key: str):
        return envelope(service().require("file", key))

    @app.post("/api/v1/files/{key}/fetch")
    def fetch(key: str, body: Destination):
        return envelope(service().fetch(key, body.destination))

    @app.post("/api/v1/parse/batches")
    def parse(body: SourceRequest, background: BackgroundTasks):
        batch, created = service().new_batch(**body.model_dump())
        if created:
            background.add_task(service().run_batch, batch["parse_batch_id"])
        return envelope(batch)

    @app.get("/api/v1/parse/batches/{key}")
    def batch_status(key: str):
        return envelope(service().require("batch", key))

    @app.get("/api/v1/parse/result/{key}")
    def parse_result(key: str):
        row = service().require("file", key)
        if not row.get("calculation_id") or row["parse_status"] in ("not_parsed", "failed"):
            raise ServiceError("NOT_PARSED", "This file requires parsing before its result is current.", 409)
        return envelope(service().calculation_detail(row["calculation_id"]))

    @app.get("/api/v1/calculations")
    def calculations(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), engine: str | None = None,
                     status: str | None = None, job: str | None = None, select: str | None = None):
        return envelope(service().calculations(limit, offset, engine, status, job, select))

    @app.get("/api/v1/calculations/{key}")
    def calculation(key: str):
        return envelope(service().calculation_detail(key))

    @app.get("/api/v1/calculations/{key}/{section}")
    def section(key: str, section: Literal["energies", "structures", "frequencies"],
                limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0),
                imaginary_only: bool = False, stage: Literal["all", "initial", "final"] = "all"):
        row = service().require("calculation", key)
        if row.get("calculation_status") == "stale":
            raise ServiceError("STALE_RESULT", "The source changed or parsing failed; reparse before reading scientific data.", 409)
        values = row[section]
        if section == "frequencies" and imaginary_only:
            values = [v for v in values if v["value"] is not None and v["value"] < 0]
        if section == "structures" and stage != "all":
            if stage == "final" and row.get("calculation_status") != "completed":
                raise ServiceError("NO_FINAL_STRUCTURE", "Output has not completed; request all observed structures instead.", 409)
            values = values[:1] if stage == "initial" else values[-1:]
        return envelope({"items": values[offset:offset + limit], "total": len(values), "offset": offset, "limit": limit})

    @app.post("/api/v1/system/backup")
    def backup():
        directory = service().home / "backups"
        directory.mkdir(exist_ok=True)
        target = directory / f"chemctl-{uuid.uuid4().hex[:12]}.sqlite3"
        service().store.backup(target)
        return envelope({"path": str(target)})

    return app
