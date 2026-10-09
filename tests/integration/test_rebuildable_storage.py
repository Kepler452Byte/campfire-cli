from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.service.project_service import ProjectService
from campfire_cli.config.settings import campfire_home


def cli(*arguments: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", "from campfire_cli.main import app; app()", *arguments],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def create(workspace: Path) -> Path:
    code = workspace / "code"
    code.mkdir()
    cli(
        "workspace",
        "project",
        "create",
        "--id",
        "product",
        "--name",
        "Product",
        "--path",
        "mywork/Product",
        "--repositories",
        json.dumps([{"id": "api", "local_path": str(code)}]),
        "--confirm",
    )
    return code


def test_database_deletion_recovers_queries_and_preserves_bindings(workspace: Path) -> None:
    code = create(workspace)
    args = [
        "document",
        "apply",
        "--path",
        "mywork/Product/Task",
        "--type",
        "task",
        "--set",
        "description=Recovery",
        "--set",
        "task_status=todo",
    ]
    preview = cli(*args)
    written = cli(*args, "--expected-hash", preview["expected_hash"], "--confirm")
    document = workspace / written["target"]
    before = document.read_bytes()
    local = (campfire_home() / "local.yaml").read_bytes()
    manifest = (workspace / ".campfire.yaml").read_bytes()
    original = cli("document", "list", "--project", "product")
    assert original["count"] >= 1
    database = campfire_home() / "campfire.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(database) + suffix).unlink(missing_ok=True)
    assert cli("workspace", "project", "show", "product")["repositories"][0]["local_path"] == str(
        code
    )
    assert not database.exists(), "Project queries must not require a database"
    recovered = cli("document", "list", "--project", "product")
    assert recovered["items"] == original["items"]
    assert (
        cli("workspace", "project", "resolve", "--path", str(code))["matches"][0]["project"]["id"]
        == "product"
    )
    assert document.read_bytes() == before
    assert (campfire_home() / "local.yaml").read_bytes() == local
    assert (workspace / ".campfire.yaml").read_bytes() == manifest
    with sqlite3.connect(database) as connection:
        tables = {
            r[0] for r in connection.execute("select name from sqlite_master where type='table'")
        }
    assert "projects" not in tables and "alembic_version" not in tables


def test_remote_has_one_source_and_repeated_setup_keeps_binding(workspace: Path) -> None:
    code = create(workspace)
    local = campfire_home() / "local.yaml"
    data = yaml.safe_load(local.read_text())
    assert data["workspaces"]["test"]["repository_bindings"] == {"product": {"api": str(code)}}
    assert "git_remote_url" not in local.read_text()
    path = workspace / ".campfire.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["projects"][0]["repositories"][0]["git_remote_url"] = "https://example.org/new.git"
    path.write_text(yaml.safe_dump(manifest))
    assert (
        cli("workspace", "project", "show", "product")["repositories"][0]["git_remote_url"]
        == "https://example.org/new.git"
    )
    cli("setup", "--path", str(workspace), "--default")
    assert yaml.safe_load(local.read_text()) == data


def test_local_write_failure_restores_manifest(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create(workspace)
    repository = FilesystemWorkspaceRepository(campfire_home())
    before = (workspace / ".campfire.yaml").read_bytes()
    project = repository.get_project("product")
    project.name = "Changed"
    project.repositories[0].local_path = str(workspace)

    def fail(*args):
        raise OSError("simulated local configuration write failure")

    monkeypatch.setattr(repository, "save_registry", fail)
    with pytest.raises(OSError):
        repository.save_project(project)
    assert (workspace / ".campfire.yaml").read_bytes() == before


def test_local_change_invalidates_project_preview(workspace: Path) -> None:
    create(workspace)
    repository = FilesystemWorkspaceRepository(campfire_home())
    service = ProjectService(campfire_home(), repository)
    preview = service.update_repository("product", "api", changes={"role": "backend"})
    local = campfire_home() / "local.yaml"
    local.write_text(local.read_text() + "\n# edited outside the CLI\n")
    from campfire_cli.common.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError) as error:
        service.update_repository(
            "product",
            "api",
            changes={"role": "backend"},
            confirm=True,
            expected_hash=preview["expected_hash"],
        )
    assert error.value.code == "project-concurrent-change"
    assert repository.get_project("product").repositories[0].role is None


def test_setup_reports_stale_binding_without_deleting_it(workspace: Path) -> None:
    create(workspace)
    local = campfire_home() / "local.yaml"
    data = yaml.safe_load(local.read_text())
    data["workspaces"]["test"]["repository_bindings"]["unknown"] = {"api": "/old/code"}
    local.write_text(yaml.safe_dump(data))
    result = cli("setup", "--path", str(workspace), "--default")
    assert result["status"] == "needs-review"
    assert result["binding_issues"] == [
        {
            "code": "repository-binding-orphaned",
            "project_id": "unknown",
            "repository_id": "api",
            "path": "/old/code",
        }
    ]
    assert yaml.safe_load(local.read_text()) == data


def test_regenerated_inventory_invalidates_old_approval(workspace: Path) -> None:
    create(workspace)
    cli("workspace", "restructure", "inventory", "--scope", "mywork/Product", "--batch", "reset")
    plan = campfire_home() / "workspaces/test/batches/reset/plan.json"
    plan.write_text(json.dumps({"items": [{"approved": True}]}))
    database = campfire_home() / "campfire.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(database) + suffix).unlink(missing_ok=True)
    cli("workspace", "restructure", "inventory", "--scope", "mywork/Product", "--batch", "reset")
    assert not plan.exists(), "Fresh inventory must not reuse previous approval"
