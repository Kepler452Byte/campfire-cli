import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem.process_lock import process_lock
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer
from campfire_cli.main import app


class MemoryScheduler:
    def __init__(self):
        self.jobs = {}
        self.fail_once = False

    def state(self, identity):
        return {
            "deployed": identity in self.jobs,
            "enabled": self.jobs.get(identity, (None, False))[1],
        }

    def deploy(self, job, enabled):
        self.jobs[job.id] = job, enabled
        if self.fail_once:
            self.fail_once = False
            raise OSError("native deployment failed halfway")

    def remove(self, identity):
        self.jobs.pop(identity, None)

    def doctor(self):
        return {"available": True}


@pytest.fixture
def service():
    service = AppContainer.build_job()
    service.scheduler = MemoryScheduler()
    yield service
    service.runs.close()


@pytest.fixture
def job(tmp_path):
    return Job(
        "example", [sys.executable, "-c", "print('hello')"], str(tmp_path), {"kind": "manual"}, 5
    )


def change(service, action, job=None, identity="example"):
    preview = service.change(action, identity, job, False, None)
    return service.change(action, identity, job, True, preview["expected_plan"])


def run(service, identity="example"):
    preview = service.run(identity, False)
    return service.run(identity, True, preview["expected_plan"])


def test_preview_manual_execution_history_and_environment(service, job):
    preview = service.change("create", job.id, job, False, None)
    assert preview["status"] == "planned" and not preview["write_performed"]
    assert not service.repository.path.exists()
    assert not (service.home / "local.yaml").exists()
    change(service, "create", job)
    identity = service.environment()["id"]
    assert len(identity) == 32
    assert service.runs.path == service.repository.path
    assert service.history(None, 20, 0) == []
    result = run(service)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["exit_code"] == 0
    assert service.environment()["id"] == identity
    assert "hello" in service.logs(result["run"]["id"], 20, 0)["chunks"][0]["content"]
    assert all(step["argv"][-1] == result["run"]["id"] for step in result["follow_up"])
    with pytest.raises(JobError) as error:
        service.change("resume", job.id, None, False, None)
    assert error.value.code == "schedule-not-applicable"
    change(service, "delete")
    assert service.list_jobs()["jobs"] == []


def test_schedule_modes_stale_plans_busy_mutations_and_compensation(service, job):
    scheduled = replace(job, schedule={"kind": "interval", "seconds": 60})
    created = change(service, "create", scheduled)
    assert not created["scheduler"]["enabled"]
    preview = service.change("resume", job.id, None, False, None)
    service.scheduler.jobs[job.id] = scheduled, True
    with pytest.raises(JobError) as error:
        service.change("resume", job.id, None, True, preview["expected_plan"])
    assert error.value.code == "stale-plan"
    assert change(service, "update", scheduled)["scheduler"]["enabled"]
    with service.run_lock(job.id), pytest.raises(JobError) as error:
        change(service, "delete")
    assert error.value.code == "busy"
    service.scheduler.fail_once = True
    before = service.repository.path.read_bytes()
    with pytest.raises(JobError) as error:
        change(service, "update", replace(scheduled, timeout=6))
    assert error.value.code == "change-failed"
    assert service.repository.path.read_bytes() == before
    assert service.scheduler.jobs[job.id] == (scheduled, True)
    assert not change(service, "update", job)["scheduler"]["deployed"]
    assert not change(service, "update", scheduled)["scheduler"]["enabled"]


@pytest.mark.parametrize(
    "mode", ["failed", "timeout", "timeout-closed", "missing", "stdin", "truncated"]
)
def test_execution_failure_timeout_eof_and_log_cap(service, job, tmp_path, mode):
    commands = {
        "failed": [sys.executable, "-c", "import sys;sys.exit(7)"],
        "timeout": [sys.executable, "-c", "import time;time.sleep(20)"],
        "timeout-closed": [
            sys.executable,
            "-c",
            "import os,time;os.close(1);os.close(2);time.sleep(20)",
        ],
        "missing": [str(tmp_path / "removed-executable")],
        "stdin": [sys.executable, "-c", "import sys;assert sys.stdin.read()=='';print('eof')"],
        "truncated": [sys.executable, "-c", "print('x'*50000)"],
    }
    definition = replace(job, argv=commands[mode], timeout=1 if mode.startswith("timeout") else 5)
    service.repository.write({job.id: definition})
    service.config["log_limit_bytes"] = 1024
    result = run(service)
    expected = {
        "failed": "failed",
        "timeout": "timeout",
        "timeout-closed": "timeout",
        "missing": "failed",
        "stdin": "succeeded",
        "truncated": "succeeded",
    }[mode]
    assert result["run"]["status"] == expected
    assert result["status"] == ("ok" if expected == "succeeded" else "error")
    if mode == "truncated":
        assert result["run"]["truncated"]
        assert (
            sum(
                len(x["content"].encode())
                for x in service.logs(result["run"]["id"], 100, 0)["chunks"]
            )
            <= 1024
        )


def test_run_preview_cannot_execute_changed_command(service, job):
    change(service, "create", job)
    preview = service.run(job.id, False)
    change(service, "update", replace(job, argv=[sys.executable, "-c", "print('changed')"]))
    with pytest.raises(JobError) as error:
        service.run(job.id, True, preview["expected_plan"])
    assert error.value.code == "stale-plan"
    assert service.history(None, 20, 0) == []


def test_workspace_filter_binding_and_execution_lock(workspace, service, job):
    bound = replace(job, workspace_id="test")
    change(service, "create", bound)
    change(service, "create", replace(job, id="other"), "other")
    result = service.list_jobs("test")
    assert [x["id"] for x in result["jobs"]] == [job.id]
    assert result["inventory_document"].startswith("_定时任务/记录-")
    import hashlib

    key = hashlib.sha256(b"test").hexdigest()
    with process_lock(service.home / f"jobs/locks/workspace-{key}.lock"):
        with pytest.raises(JobError) as error:
            run(service)
        assert error.value.code == "busy"
        assert run(service, "other")["run"]["status"] == "succeeded"
    service.resolve_workspace = lambda _: workspace / "moved"
    with pytest.raises(JobError) as error:
        run(service)
    assert error.value.code == "workspace-binding-changed"


def test_child_campfire_can_write_with_parent_workspace_execution_lock(workspace, service, job):
    definition = replace(
        job,
        workspace_id="test",
        timeout=30,
        argv=[
            sys.executable,
            "-m",
            "campfire_cli.main",
            "--workspace",
            "test",
            "document",
            "apply",
            "--path",
            "_定时任务/记录-probe.md",
            "--type",
            "record",
            "--set",
            "description=child write",
            "--expected-hash",
            "missing",
            "--confirm",
        ],
    )
    change(service, "create", definition)
    assert run(service)["run"]["status"] == "succeeded"
    target = workspace / "_定时任务/记录-probe.md"
    assert target.is_file()
    assert AppContainer.build("test").document.check(str(target))["issues"] == []


def test_upgrade_gate_and_active_run_protection(service, job):
    change(service, "create", job)
    with service.run_lock(job.id), pytest.raises(JobError), service.idle():
        pytest.fail("Upgrade must reject an active run")
    operation = "a" * 32
    folder = service.home / "upgrades" / operation
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps({"state": "running"}))
    (service.home / "active-upgrade.json").write_text(json.dumps({"operation_id": operation}))
    with pytest.raises(JobError) as error:
        run(service)
    assert error.value.code == "upgrade-active"


def test_cli_real_process_json_exit_and_no_workspace(tmp_path):
    spec = tmp_path / "job.json"
    spec.write_text(
        json.dumps(
            {
                "id": "probe",
                "argv": [
                    sys.executable,
                    "-c",
                    "import sys;print('bad',file=sys.stderr);sys.exit(7)",
                ],
                "cwd": str(tmp_path),
                "schedule": {"kind": "manual"},
            }
        )
    )
    runner = CliRunner()
    args = ["job", "create", "--file", str(spec)]
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    data = json.loads(preview.stdout)
    created = runner.invoke(app, args + ["--confirm", "--expected-plan", data["expected_plan"]])
    assert created.exit_code == 0, created.output
    preview = runner.invoke(app, ["job", "run", "probe"])
    digest = json.loads(preview.stdout)["expected_plan"]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "campfire_cli.main",
            "job",
            "run",
            "probe",
            "--confirm",
            "--expected-plan",
            digest,
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "CAMPFIRE_HOME": str(campfire_home())},
        timeout=20,
    )
    assert result.returncode == 1
    assert result.stdout == "" and len(result.stderr.splitlines()) == 1
    data = json.loads(result.stderr)
    assert data["run"]["exit_code"] == 7
    assert data["follow_up"]
    assert not (campfire_home() / "campfire.db").exists()


def test_cleanup_preview_staleness_orphan_reconcile_and_compact(service, job):
    change(service, "create", job)
    result = run(service)
    identity = result["run"]["id"]
    preview = service.cleanup(None, 0, None, False, False, None)
    assert preview["delete_count"] == 1 and not preview["write_performed"]
    assert service.result(identity)["status"] == "succeeded"
    run(service)
    with pytest.raises(JobError) as error:
        service.cleanup(None, 0, None, False, True, preview["expected_plan"])
    assert error.value.code == "stale-plan"
    preview = service.cleanup(None, 0, None, False, False, None)
    assert (
        service.cleanup(None, 0, None, False, True, preview["expected_plan"])["delete_count"] == 2
    )
    assert service.history(None, 20, 0) == []
    service.runs.start("orphan", job.id, 0, "2026-11-01T00:00:00+00:00")
    preview = service.cleanup(None, None, None, False, False, None)
    assert service.result("orphan")["status"] == "running"
    done = service.cleanup(None, None, None, False, True, preview["expected_plan"])
    assert done["reconciled_count"] == 1
    assert service.result("orphan")["status"] == "interrupted"
    preview = service.compact(False, None)
    assert service.compact(True, preview["expected_plan"])["write_performed"]


def test_environment_name_changes_keep_identity_with_readable_record_path(
    service, job, monkeypatch
):
    change(service, "create", job)
    first = service.environment()["id"], service.inventory_path()
    monkeypatch.setattr("socket.gethostname", lambda: "renamed-device")
    assert service.environment()["name"] == "renamed-device"
    assert service.environment()["id"] == first[0]
    assert service.inventory_path() == "_定时任务/记录-renamed-device.md"
    monkeypatch.setattr("socket.gethostname", lambda: "办公电脑/机房:01")
    assert service.inventory_path() == "_定时任务/记录-办公电脑-机房-01.md"


def test_list_native_failure_is_not_an_empty_success(service, job):
    change(service, "create", replace(job, schedule={"kind": "daily", "time": "23:59"}))

    def fail(_):
        raise JobError("scheduler-unavailable", "Cannot query actual state")

    service.scheduler.state = fail
    with pytest.raises(JobError) as error:
        service.list_jobs()
    assert error.value.code == "scheduler-unavailable"


def test_confirmed_write_retains_fact_if_native_state_verification_fails(service, job):
    scheduled = replace(job, schedule={"kind": "daily", "time": "23:59"})
    preview = service.change("create", job.id, scheduled, False, None)
    original = service.scheduler.state

    def state(identity):
        if identity in service.scheduler.jobs:
            raise JobError("scheduler-unavailable", "State query failed after deployment")
        return original(identity)

    service.scheduler.state = state
    result = service.change("create", job.id, scheduled, True, preview["expected_plan"])
    assert result["status"] == "blocked" and result["write_performed"]
    assert job.id in service.repository.read()


def test_definition_preview_survives_logs_but_rejects_other_definition_changes(service, job):
    change(service, "create", job)
    updated = replace(job, timeout=8)
    preview = service.change("update", job.id, updated, False, None)
    result = run(service)
    service.change("update", job.id, updated, True, preview["expected_plan"])
    assert service.result(result["run"]["id"])["status"] == "succeeded"
    preview = service.change("update", job.id, job, False, None)
    change(service, "create", replace(job, id="other"), "other")
    with pytest.raises(JobError) as error:
        service.change("update", job.id, job, True, preview["expected_plan"])
    assert error.value.code == "stale-plan"


def test_task_database_cleanup_compact_and_document_rebuild_preserve_facts(service, job):
    from campfire_cli.common.database import create_sqlite_engine, initialize_database

    change(service, "create", job)
    result = run(service)
    local = (service.home / "local.yaml").read_bytes()
    documents = create_sqlite_engine(service.home / "campfire.db")
    initialize_database(documents)
    with documents.begin() as db:
        db.exec_driver_sql("ALTER TABLE documents ADD COLUMN obsolete TEXT")
    initialize_database(documents)
    documents.dispose()
    assert service.get(job.id) == job
    assert service.logs(result["run"]["id"], 20, 0)["chunks"]
    preview = service.cleanup(None, 0, None, False, False, None)
    service.cleanup(None, 0, None, False, True, preview["expected_plan"])
    assert service.get(job.id) == job
    assert service.history(None, 20, 0) == []
    with service.runs.connection() as db:
        assert db.exec_driver_sql("SELECT count(*) FROM logs").scalar() == 0
    preview = service.compact(False, None)
    service.compact(True, preview["expected_plan"])
    assert service.get(job.id) == job
    assert (service.home / "local.yaml").read_bytes() == local
    assert not (service.home / "jobs.yaml").exists()
    assert not (service.home / "jobs/runs.db").exists()
    assert service.repository.database is service.runs.database


@pytest.mark.parametrize("damage", ["column", "table", "corrupt", "empty"])
def test_persistent_database_damage_stops_without_rebuild(service, job, damage):
    import sqlite3
    from contextlib import closing

    change(service, "create", job)
    run(service)
    service.runs.close()
    if damage in {"column", "table"}:
        with closing(sqlite3.connect(service.repository.path)) as db, db:
            db.execute(
                "ALTER TABLE runs ADD COLUMN obsolete TEXT"
                if damage == "column"
                else "DROP TABLE logs"
            )
    else:
        service.repository.path.write_bytes(b"broken database" if damage == "corrupt" else b"")
    before = service.repository.path.read_bytes()
    with pytest.raises(JobError) as error:
        service.list_jobs()
    assert error.value.code == (
        "job-database-corrupt" if damage == "corrupt" else "job-database-incompatible"
    )
    assert error.value.payload()["status"] == "blocked"
    assert service.repository.path.read_bytes() == before


def test_failed_definition_transaction_restores_definition_and_scheduler(service, job, monkeypatch):
    from sqlalchemy import event

    scheduled = replace(job, schedule={"kind": "daily", "time": "23:59"})
    change(service, "create", scheduled)
    change(service, "resume")
    engine = service.repository.database.engine

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO jobs"):
            raise RuntimeError("Injected failure after DELETE, before INSERT")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(JobError) as error:
            change(service, "update", replace(scheduled, timeout=9))
        assert error.value.code == "change-failed"
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert service.get(job.id) == scheduled
    assert service.scheduler.jobs[job.id] == (scheduled, True)


def test_database_writer_lock_is_reported_and_does_not_erase_tasks(service, job):
    import sqlite3
    from contextlib import closing

    change(service, "create", job)
    with closing(sqlite3.connect(service.repository.path)) as locked:
        locked.execute("BEGIN IMMEDIATE")
        with pytest.raises(JobError) as error:
            service.repository.write({})
        assert error.value.code == "job-database-busy"
        assert service.get(job.id) == job
        locked.rollback()
    assert service.get(job.id) == job


def test_old_storage_is_not_read_or_silently_presented_as_empty(service):
    source = service.home / "jobs.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("invalid obsolete configuration")
    before = source.read_bytes()
    with pytest.raises(JobError) as error:
        service.list_jobs()
    assert error.value.code == "job-storage-required"
    assert source.read_bytes() == before
    assert not service.repository.path.exists()


def test_compact_rejects_an_active_connection_and_definition_change(service, job):
    from campfire_cli.common.exceptions import GovernanceBlockedError

    change(service, "create", job)
    preview = service.compact(False, None)
    with service.runs.connection(), pytest.raises(GovernanceBlockedError) as error:
        service.compact(True, preview["expected_plan"])
    assert error.value.code == "database-busy"
    assert service.get(job.id) == job
    preview = service.compact(False, None)
    change(service, "update", replace(job, name="Updated name"))
    with pytest.raises(JobError) as error:
        service.compact(True, preview["expected_plan"])
    assert error.value.code == "stale-plan"
