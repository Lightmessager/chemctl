import json
import os
import time
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from . import eggs
from .client import APIError, Client

app = typer.Typer(help="chemctl: local chemistry data and explicit mock jobs.")
eggs.register(app)


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        eggs.banner()
        typer.echo(ctx.get_help())



system = typer.Typer(help="Service health and database backup.")
server = typer.Typer(help="Server configuration and SSH probes.")
job = typer.Typer(help="PBS jobs and explicit demo simulations.")
files = typer.Typer(help="Local output indexing and export.")
parse = typer.Typer(help="Background parsing with cclib.")
data = typer.Typer(help="Scientific summaries and source references.")
config = typer.Typer(help="Local service configuration.")
for name, group in [("system", system), ("server", server), ("job", job), ("file", files), ("parse", parse), ("data", data), ("config", config)]:
    app.add_typer(group, name=name)

Format = Annotated[str, typer.Option("--format", help="json (default, stable for scripts and AI), text (indented JSON) or table (colour, for people); structures also accepts xyz")]

GOOD = {"ok", "parsed", "completed", "succeeded", "True", "available"}
WAIT = {"partial", "incomplete", "queued", "running", "unknown", "not_parsed", "not_checked", "partially_succeeded", "unsupported"}
BAD = {"failed", "stale", "cancelled", "False"}
NOISY = {"content_hash", "source_fingerprint", "mtime_ns", "idempotency_key", "input_manifest", "atom_symbols", "coordinates", "symbols"}


def cell(value, width=64):
    from rich.text import Text
    if value is None:
        return Text("—", style="dim")
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    style = "green" if text in GOOD else "yellow" if text in WAIT else "red" if text in BAD else ""
    return Text(text if len(text) <= width else text[:width - 1] + "…", style=style)


def table(result):
    """Human view of the same envelope. Values are shown as returned; long ones are shortened for display only."""
    from rich.console import Console
    from rich.table import Table
    data, console = result["data"], Console()
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        rows = data["items"]
        first = rows[0] if rows and isinstance(rows[0], dict) else {}
        # Nested values and secondary ids stay in --format json; the table keeps what fits on a line.
        columns = [key for key, value in first.items() if key not in NOISY and not isinstance(value, (dict, list))
                   and not (key == "file_id" and "calculation_id" in first)]
        view = Table(header_style="bold cyan", border_style="dim", row_styles=["", "dim"] if len(rows) > 6 else None)
        for key in columns:
            view.add_column(key, overflow="fold")
        for item in rows:
            view.add_row(*(cell(item.get(key), 40) for key in columns))
        console.print(view if columns else "[dim]no rows[/dim]")
        console.print(f"[dim]total {data['total']} · offset {data['offset']} · limit {data['limit']}[/dim]")
    elif isinstance(data, dict):
        view = Table(show_header=False, border_style="dim")
        view.add_column(style="bold cyan")
        view.add_column(overflow="fold")
        for key, value in data.items():
            view.add_row(key, cell(value, 100))
        console.print(view)
    else:
        console.print(cell(data, 2000))


def output(result, fmt="json"):
    if fmt == "table":
        return table(result)
    if fmt not in ("json", "text"):
        raise typer.BadParameter("format must be json, text or table")
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2 if fmt == "text" else None, allow_nan=False))


@app.command()
def serve(port: int = 8765, home: Path | None = None):
    """Start the shared API on loopback; API docs at /docs."""
    import uvicorn
    from .api import create_app
    uvicorn.run(create_app(home), host="127.0.0.1", port=port)


@app.command()
def gui():
    """Open the desktop client (start the API first)."""
    from .gui import main as launch
    launch()


@app.command()
def schema():
    """Print the machine-readable OpenAPI schema."""
    output(Client().call("GET", "/openapi.json"))


@system.command()
def health(format: Format = "json"):
    output(Client().get("/health"), format)


@system.command()
def backup(format: Format = "json"):
    output(Client().post("/system/backup"), format)


@config.command("show")
def config_show(format: Format = "json"):
    output(Client().get("/health"), format)


@config.command("path")
def config_path():
    output({"url": Client().url, "home": os.environ.get("CHEMCTL_HOME", "platform user data directory")})


@server.command("list")
def server_list(limit: int = 50, offset: int = 0, format: Format = "json"):
    output(Client().get("/servers", limit=limit, offset=offset), format)


@server.command("test")
def server_test(server_id: str, password_prompt: bool = False, format: Format = "json"):
    """Probe SSH; --password-prompt reads a password without echo or persistence."""
    import getpass
    password = getpass.getpass("SSH password (not saved): ") if password_prompt else None
    output(Client().post(f"/servers/{server_id}/test", password=password), format)


@server.command("configure")
def server_configure(server_id: str, host: str, remote_root: str, name: str = "AnySCP", username: str | None = None,
                     scheduler: str = "unknown", port: int | None = None, format: Format = "json"):
    output(Client().post("/servers", server_id=server_id, host=host, remote_root=remote_root,
                         name=name, username=username, scheduler=scheduler, port=port), format)


@server.command("enable-key")
def server_enable_key(server_id: str, format: Format = "json"):
    """Install a dedicated public key using the active session; protect the private key with Windows DPAPI."""
    output(Client().post(f"/servers/{server_id}/enable-key"), format)


@server.command("software")
def server_software(server_id: str, format: Format = "json"):
    """Locate ORCA/Gaussian without starting calculations."""
    output(Client().post(f"/servers/{server_id}/software"), format)


@job.command("submit")
def submit(input: Annotated[Path, typer.Option("--input")], server: str = "demo", engine: str = "orca",
           profile: str = "default", tag: str = "", dry_run: bool = False,
           idempotency_key: str | None = None, script: str | None = None, format: Format = "json"):
    """Submit an explicit PBS script or demo job. Use --dry-run to inspect the complete plan."""
    output(Client().post("/jobs", input_path=str(input.resolve()), server_id=server, engine=engine,
                         profile=profile, tag=tag, dry_run=dry_run, script=script, idempotency_key=idempotency_key or str(uuid4())), format)


@job.command("list")
def job_list(status: str | None = None, server: str | None = None, limit: int = 20, offset: int = 0, format: Format = "json"):
    output(Client().get("/jobs", status=status, server=server, limit=limit, offset=offset), format)


@job.command("status")
def job_status(job_id: str, refresh: bool = False, format: Format = "json"):
    output(Client().post(f"/jobs/{job_id}/refresh") if refresh else Client().get(f"/jobs/{job_id}"), format)


@job.command("sync")
def job_sync(job_id: str, parse: bool = True, format: Format = "json"):
    """Start SFTP output synchronization; job status reports sync_status and parse_batch_id."""
    output(Client().post(f"/jobs/{job_id}/sync", parse=parse), format)


@job.command("diagnose")
def diagnose(job_id: str, format: Format = "json"):
    output(Client().get(f"/jobs/{job_id}/diagnose"), format)


@job.command("cancel")
def cancel(job_id: str, yes: Annotated[bool, typer.Option("--yes", help="Confirm cancellation of this job")] = False, format: Format = "json"):
    if not yes:
        raise APIError({"ok": False, "data": None, "error": {"code": "CONFIRMATION_REQUIRED", "message": "Repeat with --yes to cancel this job."}, "meta": {}})
    output(Client().post(f"/jobs/{job_id}/cancel"), format)


@job.command("advance-mock")
def advance(job_id: str, format: Format = "json"):
    """Advance a demo job queued -> running -> completed; executes no calculation."""
    output(Client().post(f"/jobs/{job_id}/advance-mock"), format)


@job.command("wait")
def wait(job_id: str, until: str = "completed", timeout: float = 3600, interval: float = 30, format: Format = "json"):
    if interval <= 0 or timeout < 0:
        raise typer.BadParameter("interval must be positive and timeout nonnegative")
    deadline = time.monotonic() + timeout
    while True:
        result = Client().post(f"/jobs/{job_id}/refresh")
        state = result["data"]["status"]
        if state == until:
            output(result, format)
            return
        if state in ("cancelled", "failed", "completed") or time.monotonic() >= deadline:
            output(result, format)
            raise typer.Exit(2)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


@files.command("scan")
def file_scan(path: Path, recursive: bool = False, format: Format = "json"):
    output(Client().post("/files/scan", source=str(path.resolve()), recursive=recursive), format)


@files.command("list")
def file_list(limit: int = 50, offset: int = 0, status: str | None = None, format: Format = "json"):
    output(Client().get("/files", limit=limit, offset=offset, status=status), format)


@files.command("info")
def file_info(file_id: str, format: Format = "json"):
    output(Client().get(f"/files/{file_id}"), format)


@files.command("fetch")
def file_fetch(file_id: str, to: Annotated[Path, typer.Option("--to")], format: Format = "json"):
    output(Client().post(f"/files/{file_id}/fetch", destination=str(to.resolve())), format)


@parse.command("batch")
def parse_batch(source: Annotated[Path, typer.Option("--source")], recursive: bool = True, force: bool = False,
                idempotency_key: str | None = None, format: Format = "json"):
    output(Client().post("/parse/batches", source=str(source.resolve()), recursive=recursive, force=force,
                         idempotency_key=idempotency_key), format)


@parse.command("status")
def parse_status(parse_batch_id: str, format: Format = "json"):
    output(Client().get(f"/parse/batches/{parse_batch_id}"), format)


@parse.command("result")
def parse_result(file_id: str, format: Format = "json"):
    output(Client().get(f"/parse/result/{file_id}"), format)


@parse.command("reparse")
def reparse(file_id: str, format: Format = "json"):
    row = Client().get(f"/files/{file_id}")["data"]
    output(Client().post("/parse/batches", source=row["local_path"], recursive=False, force=True), format)


@data.command("query")
def query(job: str | None = None, engine: str | None = None, status: str | None = None,
          select: str | None = None, limit: int = 20, offset: int = 0, format: Format = "json"):
    output(Client().get("/calculations", job=job, engine=engine, status=status, select=select, limit=limit, offset=offset), format)


@data.command("energies")
def energies(calculation_id: str, limit: int = 50, offset: int = 0, format: Format = "json"):
    """Return observed electronic energies in Eh with source line numbers."""
    output(Client().get(f"/calculations/{calculation_id}/energies", limit=limit, offset=offset), format)


@data.command("frequencies")
def frequencies(calculation_id: str, imaginary_only: bool = False, limit: int = 50, offset: int = 0, format: Format = "json"):
    output(Client().get(f"/calculations/{calculation_id}/frequencies", imaginary_only=imaginary_only, limit=limit, offset=offset), format)


def as_xyz(structure):
    rows = [str(len(structure["symbols"])), "chemctl | angstrom | " + str(structure["source_location"])]
    rows += [f"{symbol:2s} {xyz[0]:.10f} {xyz[1]:.10f} {xyz[2]:.10f}" for symbol, xyz in zip(structure["symbols"], structure["coordinates"])]
    return "\n".join(rows)


@data.command("structures")
def structures(calculation_id: str, stage: str = "final", limit: int = 50, offset: int = 0, format: Format = "json"):
    result = Client().get(f"/calculations/{calculation_id}/structures", stage=stage, limit=limit, offset=offset)
    if format == "xyz":
        typer.echo("\n".join(as_xyz(row) for row in result["data"]["items"]))
    else:
        output(result, format)


def main():
    try:
        app()
    except APIError as exc:
        output(exc.response)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
