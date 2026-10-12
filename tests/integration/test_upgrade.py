import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from campfire_cli.app.system.service.upgrade_service import UpgradeService
from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceEntry
from campfire_cli.common.package_updater import PackageUpdater
from campfire_cli.common.package_version import installed_version
from campfire_cli.container import AppContainer
from campfire_cli.main import app


def test_offline_upgrade_never_queries_network(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Offline upgrade queried the network")

    monkeypatch.setattr(
        "campfire_cli.app.system.service.upgrade_service.fetch_latest_version", forbidden
    )
    result = AppContainer.build_upgrade().upgrade(skip_package=True)
    assert result["status"] == "ok"
    assert result["package"]["action"] == "skipped-by-flag"
    queried = AppContainer.build_upgrade().status(result["operation_id"])
    assert queried["state"] == "completed"
    assert queried["package_stage"] == "skipped"
    assert queried["resource_stage"] == "completed"


def test_resource_failure_is_durable_and_cli_fails(tmp_path):
    (tmp_path / "agent-skills" / "campfire-context-bootstrap").mkdir(parents=True)
    (tmp_path / "agent-skills" / "campfire-context-bootstrap" / "SKILL.md").write_text(
        "---\nname: foreign\n---\n", encoding="utf-8"
    )
    result = CliRunner().invoke(app, ["upgrade", "--skip-package"])
    assert result.exit_code == 3
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    payload = json.loads(result.stderr)
    queried = AppContainer.build_upgrade().status(payload["operation_id"])
    assert queried["state"] == "failed"
    assert queried["resource_stage"] == "failed"


def test_invalid_hint_preflight_is_queryable(tmp_path):
    (tmp_path / "agent-hints").write_bytes(b"<!-- campfire:agent-hints:start -->")
    result = AppContainer.build_upgrade().upgrade(skip_package=True)
    assert result["status"] == "blocked"
    queried = AppContainer.build_upgrade().status(result["operation_id"])
    assert queried["state"] == "failed"
    assert queried["resources"]["skills"]["issues"][0]["code"] == "invalid-markers"


def test_invalid_operation_id_has_input_contract(tmp_path):
    result = CliRunner().invoke(app, ["agent", "upgrade-status", "../outside"])
    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["code"] == "invalid-input"
    assert payload["field"] == "operation_id"
    assert payload["expected_type"] == "string"
    assert not (tmp_path / "campfire-home").exists()


def test_multiple_workspaces_report_failure_and_preserve_templates(workspace):
    repository = FilesystemWorkspaceRepository(workspace / "_campfire")
    registry = repository.load_registry()
    registry.workspaces["missing"] = WorkspaceEntry(path=str(workspace / "missing"))
    repository.save_registry(registry)
    template = workspace / "_模板" / "custom.md"
    template.parent.mkdir()
    template.write_bytes(b"user template\r\n")
    result = AppContainer.build_upgrade().upgrade(skip_package=True)
    assert result["status"] == "blocked"
    items = {item["workspace_id"]: item for item in result["workspaces"]}
    assert items["test"]["status"] == "ok"
    assert items["missing"]["status"] == "blocked"
    assert "bases" in items["missing"]["skipped"]
    assert template.read_bytes() == b"user template\r\n"


@pytest.mark.parametrize("args", [["version"], ["--version"], ["-V"], ["tree"]])
def test_discovery_does_not_create_state(tmp_path, args):
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ok"
    assert not (tmp_path / "campfire-home").exists()


def test_editable_and_offline_package_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "campfire_cli.app.system.service.upgrade_service.fetch_latest_version", lambda _: None
    )
    for manager, supported, action in [
        ("editable", False, "skipped-editable"),
        ("unknown", False, "skipped-unknown"),
        ("uv-tool", True, "skipped-offline"),
    ]:
        updater = PackageUpdater("campfire-cli", "campfire", tmp_path / manager)
        monkeypatch.setattr(
            updater,
            "plan",
            lambda m=manager, s=supported: {
                "manager": m,
                "supported": s,
                "hint": "repair installation",
            },
        )
        system = SimpleNamespace(align=lambda: {"status": "ok", "workspaces": []})
        result = UpgradeService(system, updater).upgrade()
        assert result["package"]["action"] == action
        assert (
            UpgradeService(system, updater).status(result["operation_id"])["state"] == "completed"
        )


@pytest.mark.parametrize(
    "manager_exit,target,state,package_stage,resource_stage",
    [
        (0, None, "completed", "completed", "completed"),
        (5, None, "failed", "failed", "skipped"),
        (0, "999.0.0", "failed", "failed", "skipped"),
    ],
)
def test_detached_worker_executes_and_waits_for_host(
    tmp_path, manager_exit, target, state, package_stage, resource_stage
):
    root = tmp_path / "upgrade state with spaces"
    executable = Path(sys.prefix) / ("Scripts/campfire.exe" if os.name == "nt" else "bin/campfire")
    plan = {
        "current_version": installed_version(),
        "target_version": target,
        "update_command": [sys.executable, "-c", f"raise SystemExit({manager_exit})"],
        "entry_point": str(executable),
    }
    host_code = (
        "import json,time\n"
        "from pathlib import Path\n"
        "from campfire_cli.common.package_updater import PackageUpdater,plan_digest\n"
        f"updater=PackageUpdater('campfire-cli','campfire',Path({str(root)!r}))\n"
        f"plan=json.loads({json.dumps(plan)!r})\n"
        "job=updater.start(plan,plan_digest(plan))\n"
        "print(json.dumps(job),flush=True)\n"
        "time.sleep(1)\n"
    )
    with subprocess.Popen(
        [sys.executable, "-c", host_code], stdout=subprocess.PIPE, text=True, encoding="utf-8"
    ) as host:
        job = json.loads(host.stdout.readline())
        updater = PackageUpdater("campfire-cli", "campfire", root)
        during = updater.status(job["operation_id"])
        assert during["package_stage"] == "pending"
        assert not (tmp_path / "agent-skills").exists()
        host.wait(timeout=10)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = updater.status(job["operation_id"])
        if result["state"] in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert result["state"] == state, Path(job["log_path"]).read_text(encoding="utf-8")
    assert result["package_stage"] == package_stage
    assert result["resource_stage"] == resource_stage
    if state == "failed":
        assert not (tmp_path / "agent-skills").exists()
