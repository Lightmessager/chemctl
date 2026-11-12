from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from chemctl.api import create_app
from chemctl.parsing import parse_output

FIXTURES = Path(__file__).parent.parent / "examples"


def test_partial_output_never_claims_final_energy(tmp_path):
    source = tmp_path / "partial.out"
    source.write_text("                         O   R   C   A\nFINAL SINGLE POINT ENERGY     -75.12345\n")
    result = parse_output(source)
    assert result["status"] == "partial"
    assert result["final_energy_eh"] is None
    assert result["energies"][0]["value"] == -75.12345
    assert result["energies"][0]["source_location"]["line"] == 2
    source.write_text(source.read_text() + "ORCA TERMINATED NORMALLY\nO   R   C   A\n")
    appended = parse_output(source)
    assert appended["calculation_status"] == "incomplete"
    assert appended["final_energy_eh"] is None


def test_local_workflow_and_idempotency(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/v1/health").json()["data"]["database"] == "ok"
        local_outputs = tmp_path / "outputs"
        shutil.copytree(FIXTURES, local_outputs)
        request = {"source": str(local_outputs), "recursive": True}
        batch = client.post("/api/v1/parse/batches", json=request).json()["data"]
        result = client.get(f'/api/v1/parse/batches/{batch["parse_batch_id"]}').json()["data"]
        assert result["status"] == "succeeded"
        assert result["processed"] == 2
        rows = client.get("/api/v1/calculations").json()["data"]["items"]
        assert len(rows) == 2
        assert {r["engine"] for r in rows} == {"orca", "gaussian09d"}
        second = client.post("/api/v1/parse/batches", json=request).json()["data"]
        second = client.get(f'/api/v1/parse/batches/{second["parse_batch_id"]}').json()["data"]
        assert second["skipped"] == 2
        changed = local_outputs / "orca-demo.out"
        changed.write_text(changed.read_text() + "O   R   C   A\n")
        client.post("/api/v1/files/scan", json=request)
        stale = next(row for row in client.get("/api/v1/calculations").json()["data"]["items"] if row["engine"] == "orca")
        assert stale["final_energy_eh"] is None
        assert stale["status"] == "not_parsed"
        assert client.get(f'/api/v1/parse/result/{stale["file_id"]}').status_code == 409
        inp = tmp_path / "water.inp"
        inp.write_text("! HF STO-3G\n* xyz 0 1\nH 0 0 0\nH 0 0 0.7\n*\n")
        job_request = {"server_id": "demo", "input_path": str(inp), "engine": "orca", "idempotency_key": "test-submit"}
        first = client.post("/api/v1/jobs", json=job_request).json()["data"]
        again = client.post("/api/v1/jobs", json=job_request).json()["data"]
        assert first["job_id"] == again["job_id"]
        assert first["simulated"] is True
        assert client.post(f'/api/v1/jobs/{first["job_id"]}/cancel').json()["data"]["status"] == "cancelled"
        missing = client.get("/api/v1/jobs/missing")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"
    with TestClient(create_app(tmp_path)) as restarted:
        assert restarted.get("/api/v1/calculations").json()["data"]["total"] == 2
