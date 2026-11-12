from pathlib import Path
import pytest

from chemctl.remote_jobs import pbs_state, wrapper_script, prepare_plan
from chemctl.errors import ServiceError


def test_pbs_terminal_evidence_and_script(tmp_path):
    assert pbs_state("Job Id: 12.host\n    job_state = R\n")["status"] == "running"
    assert pbs_state("Job Id: 12.host\n    job_state = C\n    exit_status = 0\n")["status"] == "completed"
    assert pbs_state("Job Id: 12.host\n    job_state = C\n")["status"] == "unknown"
    script = wrapper_script("#PBS -l nodes=1:ppn=1\necho hello\n", "run.sh", "/home/u/jobs/job_1")
    assert "#PBS -l nodes=1:ppn=1" in script
    assert "trap" in script and ".chemctl-exit" in script
    assert "bash ./run.sh" in script
    assert "bash -e ./run.sh" in wrapper_script("#!/bin/bash -e\nfalse\necho done\n", "run.sh", "/home/u/jobs/job_1")


def test_remote_plan_requires_verified_pbs_and_explicit_script(tmp_path):
    (tmp_path / "run.sh").write_text("#PBS -l nodes=1:ppn=1\necho hello\n")
    server = {"server_id": "s", "scheduler": "unknown", "remote_root": "/home/u/jobs",
              "last_probe": {"detected_scheduler": "unknown"}}
    request = {"input_path": str(tmp_path), "script": "run.sh", "idempotency_key": "a", "engine": "orca", "tag": "demo", "profile": "default", "server_id": "s"}
    with pytest.raises(ServiceError, match="confirmed"):
        prepare_plan(server, request)
    server["last_probe"]["detected_scheduler"] = "pbs"
    plan = prepare_plan(server, request)
    assert plan["remote_directory"].startswith("/home/u/jobs/job_")
    assert plan["script_text"].endswith("echo hello\n")
    assert plan["simulated"] is False
    request["script"] = "../other.sh"
    with pytest.raises(ServiceError):
        prepare_plan(server, request)


def test_restart_recovers_submit_and_sync_intent(tmp_path):
    from chemctl.service import Service
    service = Service(tmp_path)
    service.store.put("job", "j", {"job_id": "j", "simulated": False, "status": "submitting", "sync_status": "running"})
    service.close()
    restarted = Service(tmp_path)
    row = restarted.require("job", "j")
    assert row["status"] == "submission_unknown"
    assert row["sync_status"] == "failed"
    restarted.close()
