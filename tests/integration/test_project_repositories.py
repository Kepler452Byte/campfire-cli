from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import (
    WorkspaceManifest,
)
from campfire_cli.app.workspace.service.project_service import ProjectService
from campfire_cli.common.database import upgrade_database
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.config.settings import campfire_home
from campfire_cli.main import app

runner = CliRunner()


def cli(*arguments: str) -> dict:
    result = runner.invoke(app, list(arguments))
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def create_project(workspace: Path, repositories: list[dict], project_id: str = "product") -> dict:
    return cli(
        "workspace",
        "project",
        "create",
        "--id",
        project_id,
        "--name",
        "Product",
        "--path",
        f"mywork/{project_id}",
        "--repositories",
        json.dumps(repositories),
        "--confirm",
    )


def update_repository(repository_id: str, *arguments: str) -> dict:
    args = [
        "workspace",
        "project",
        "update",
        "--id",
        "product",
        "--repository",
        repository_id,
        *arguments,
    ]
    preview = cli(*args)
    assert preview["write_performed"] is False
    return cli(*args, "--expected-hash", preview["expected_hash"], "--confirm")


def test_multiple_repositories_preserve_identity_and_other_bindings(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend = workspace / "frontend"
    backend = frontend / "api"
    backend.mkdir(parents=True)
    project = create_project(
        workspace,
        [
            {"id": "web", "role": "frontend", "local_path": str(frontend)},
            {"id": "api", "role": "backend", "local_path": str(backend)},
        ],
    )["project"]
    assert "git_remote_url" not in project and "local_path" not in project
    calls = []
    monkeypatch.setattr(ProjectService, "_git_command", lambda *args: calls.append(args))
    match = cli("workspace", "project", "resolve", "--path", str(backend / "src"))
    assert match["status"] == "matched"
    assert match["matches"][0]["repository_id"] == "api"
    assert match["matches"][0]["project"]["id"] == "product"
    assert calls == []
    updated = update_repository("web", "--role", "ui")["project"]
    assert [item["id"] for item in updated["repositories"]] == ["web", "api"]
    assert updated["repositories"][1]["local_path"] == str(backend)
    unbound = update_repository("web", "--unbind")["project"]
    assert unbound["repositories"][0]["local_path"] is None
    removed = update_repository("web", "--remove-repository")["project"]
    assert removed["repositories"][0]["id"] == "api"
    assert backend.is_dir() and frontend.is_dir()
    assert removed["document_domain_id"] == project["document_domain_id"]
    manifest = yaml.safe_load((workspace / ".campfire.yaml").read_text())
    assert manifest["schema_version"] == 2
    assert "local_path" not in json.dumps(manifest)
    assert "git_remote_url" not in manifest["projects"][0]


def test_new_device_import_and_repeated_setup_preserve_bindings_by_id(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project(
        workspace,
        [
            {"id": "web", "git_remote_url": "https://example.org/web.git"},
            {"id": "api", "git_remote_url": "https://example.org/api.git"},
        ],
    )
    monkeypatch.setenv("CAMPFIRE_HOME", str(workspace / "other-device"))
    setup = cli("setup", "--path", str(workspace), "--default")
    assert setup["status"] == "needs-input"
    assert {item["repository_id"] for item in setup["unbound_repositories"]} == {"web", "api"}
    assert all(
        item["required_input"] == {"local-path": "existing local directory path"}
        for item in setup["unbound_repositories"]
    )
    local = workspace / "cloned-web"
    local.mkdir()
    cli(
        "workspace",
        "project",
        "bind",
        "--id",
        "product",
        "--repository",
        "web",
        "--local-path",
        str(local),
    )
    manifest_path = workspace / ".campfire.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["projects"][0]["repositories"].reverse()
    manifest_path.write_text(yaml.safe_dump(manifest))
    repeated = cli("setup", "--path", str(workspace), "--default")
    assert [item["repository_id"] for item in repeated["unbound_repositories"]] == ["api"]
    project = cli("workspace", "project", "show", "product")
    assert next(item for item in project["repositories"] if item["id"] == "web")[
        "local_path"
    ] == str(local)
    assert "local_path" not in manifest_path.read_text()


def test_repository_mutations_reject_concurrent_manifest_and_database_changes(
    workspace: Path,
) -> None:
    create_project(workspace, [{"id": "web"}, {"id": "api"}])
    args = [
        "workspace",
        "project",
        "update",
        "--id",
        "product",
        "--repository",
        "web",
        "--role",
        "ui",
    ]
    preview = cli(*args)
    manifest = workspace / ".campfire.yaml"
    manifest.write_text(manifest.read_text() + "\n# externally edited\n")
    changed = runner.invoke(app, [*args, "--expected-hash", preview["expected_hash"], "--confirm"])
    assert json.loads(changed.output)["code"] == "project-concurrent-change"
    assert cli("workspace", "project", "show", "product")["repositories"][0]["role"] is None
    preview = cli(*args)
    update_repository("api", "--role", "server")
    changed = runner.invoke(app, [*args, "--expected-hash", preview["expected_hash"], "--confirm"])
    assert json.loads(changed.output)["code"] == "project-concurrent-change"


def test_single_repository_uses_same_explicit_interface(workspace: Path) -> None:
    local = workspace / "code"
    local.mkdir()
    created = create_project(workspace, [{"id": "source", "local_path": str(local)}])
    assert created["project"]["repositories"][0]["id"] == "source"
    assert "local_path" not in created["project"]
    without_id = runner.invoke(
        app, ["workspace", "project", "bind", "--id", "product", "--local-path", str(local)]
    )
    assert without_id.exit_code != 0
    invalid = runner.invoke(
        app, ["workspace", "project", "update", "--id", "product", "--default-branch", "main"]
    )
    assert json.loads(invalid.output)["code"] == "repository-selection-required"
    single = update_repository("source", "--default-branch", "trunk")["project"]
    assert single["repositories"][0]["default_branch"] == "trunk"
    assert "default_branch" not in single
    update_repository("api", "--git-remote-url", "https://example.org/api.git")
    renamed = cli("workspace", "project", "update", "--id", "product", "--name", "Renamed")
    assert len(renamed["repositories"]) == 2
    assert renamed["repositories"][0]["default_branch"] == "trunk"


def test_validation_and_manifest_path_boundaries(workspace: Path) -> None:
    for value, code in [
        ("{}", "invalid-repositories"),
        ('[{"id":"web"},{"id":"web"}]', "repository-id-duplicate"),
        ('[{"id":"web","unknown":true}]', "invalid-repositories"),
    ]:
        result = runner.invoke(
            app,
            [
                "workspace",
                "project",
                "create",
                "--id",
                "product",
                "--name",
                "Product",
                "--path",
                "mywork/product",
                "--repositories",
                value,
                "--confirm",
            ],
        )
        payload = json.loads(result.output)
        assert payload["code"] == code
        assert payload["field"] == "repositories"
        assert not (workspace / "mywork/product").exists()
    with pytest.raises(ValueError, match="local_path"):
        WorkspaceManifest.model_validate(
            {
                "workspace": {"id": "x", "name": "X"},
                "projects": [
                    {
                        "id": "p",
                        "name": "P",
                        "document_domain_id": "d",
                        "repositories": [{"id": "r", "local_path": "/private/code"}],
                    },
                ],
            }
        )


def test_manifest_failure_rolls_back_repository_change(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_project(workspace, [{"id": "web"}])
    repository = SqliteWorkspaceRepository(campfire_home())
    service = ProjectService(campfire_home(), repository)
    preview = service.update_repository("product", "api", changes={})
    before = repository.get_project("product")

    def fail(*args):
        raise OSError("simulated manifest failure")

    monkeypatch.setattr(service._manifests, "save", fail)
    with pytest.raises(OSError):
        service.update_repository(
            "product", "api", changes={}, confirm=True, expected_hash=preview["expected_hash"]
        )
    assert repository.get_project("product") == before


def test_remote_matches_remain_candidates_and_check_reports_repository(workspace: Path) -> None:
    local = workspace / "git-repository"
    local.mkdir()
    subprocess.run(["git", "init", str(local)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(local), "remote", "add", "origin", "https://example.org/shared.git"],
        check=True,
        capture_output=True,
    )
    create_project(
        workspace,
        [
            {"id": "web", "git_remote_url": "git@example.org:shared.git"},
            {"id": "api", "git_remote_url": "https://example.org/shared.git"},
        ],
    )
    result = cli("workspace", "project", "resolve", "--path", str(local))
    assert result["status"] == "unmatched"
    assert {item["repository_id"] for item in result["remote_matches"]} == {"web", "api"}
    cli(
        "workspace",
        "project",
        "bind",
        "--id",
        "product",
        "--repository",
        "web",
        "--local-path",
        str(local),
    )
    subprocess.run(
        ["git", "-C", str(local), "remote", "set-url", "origin", "https://example.org/changed.git"],
        check=True,
        capture_output=True,
    )
    checked = cli("workspace", "project", "check", "product")
    assert {(item["code"], item["repository_id"]) for item in checked["issues"]} == {
        ("project-git-remote-changed", "web"),
        ("project-repository-unbound", "api"),
    }


def test_database_012_migration_is_lossless_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            INSERT INTO alembic_version VALUES ('012');
            CREATE TABLE projects (id TEXT PRIMARY KEY, git_remote_url TEXT,
                                   local_path TEXT, default_branch TEXT);
            INSERT INTO projects VALUES ('product', 'git@example.org:api.git', '/old/api', 'main');
        """)
    upgrade_database(database)
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT repositories FROM projects").fetchone()
        columns = {item[1] for item in connection.execute("PRAGMA table_info(projects)")}
    assert json.loads(row[0]) == [
        {
            "id": "default",
            "git_remote_url": "git@example.org:api.git",
            "local_path": "/old/api",
            "default_branch": "main",
        }
    ]
    assert not columns & {"git_remote_url", "local_path", "default_branch"}
    from campfire_cli.app.workspace.repository.manifest_repository import (
        WorkspaceManifestRepository,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    manifest_path = vault / ".campfire.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "workspace": {"id": "test", "name": "Test"},
                "projects": [
                    {
                        "id": "product",
                        "name": "Product",
                        "document_domain_id": "root",
                        "git_remote_url": "git@example.org:api.git",
                        "default_branch": "main",
                    }
                ],
            }
        )
    )
    repository = WorkspaceManifestRepository()
    assert repository.upgrade(vault) is True
    upgraded = manifest_path.read_bytes()
    assert repository.upgrade(vault) is False
    assert manifest_path.read_bytes() == upgraded
    portable = repository.load(vault)
    assert portable.projects[0].repositories[0].id == "default"
    assert portable.projects[0].repositories[0].git_remote_url == "git@example.org:api.git"


def test_equal_depth_paths_are_explicitly_ambiguous(workspace: Path) -> None:
    local = workspace / "shared-directory"
    local.mkdir()
    create_project(
        workspace,
        [{"id": "web", "local_path": str(local)}, {"id": "api", "local_path": str(local)}],
    )
    result = cli("workspace", "project", "resolve", "--path", str(local))
    assert result["status"] == "ambiguous"
    assert result["git_remote_url"] is None
    assert len(result["matches"]) == 2


def test_export_import_preserves_all_local_bindings(workspace: Path) -> None:
    create_project(workspace, [{"id": "web"}, {"id": "api"}])
    backup = workspace / "registry.json"
    cli("workspace", "export", "--output", str(backup))
    original = cli("workspace", "project", "show", "product")
    update_repository("web", "--remove-repository")
    cli("workspace", "import", "--input", str(backup), "--confirm")
    assert cli("workspace", "project", "show", "product") == original


def test_domain_rekey_keeps_repositories_and_local_bindings(workspace: Path) -> None:
    local = workspace / "code"
    local.mkdir()
    create_project(workspace, [{"id": "web", "local_path": str(local)}, {"id": "api"}])
    original = cli("workspace", "project", "show", "product")
    cli(
        "workspace",
        "domain",
        "rekey",
        "--domain",
        "project-product",
        "--new-id",
        "product-docs",
        "--confirm",
    )
    updated = cli("workspace", "project", "show", "product")
    assert updated["document_domain_id"] == "product-docs"
    assert updated["repositories"] == original["repositories"]
    manifest = yaml.safe_load((workspace / ".campfire.yaml").read_text())
    assert manifest["projects"][0]["document_domain_id"] == "product-docs"
    assert {item["id"] for item in manifest["projects"][0]["repositories"]} == {"web", "api"}
    assert "local_path" not in json.dumps(manifest)


def test_manifest_upgrade_preserves_local_only_repository_and_rejects_invalid_source(
    workspace: Path,
) -> None:
    from campfire_cli.app.workspace.repository.manifest_repository import (
        WorkspaceManifestRepository,
    )

    local = workspace / "source"
    local.mkdir()
    create_project(workspace, [{"id": "default", "local_path": str(local)}])
    manifest_path = workspace / ".campfire.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["schema_version"] = 1
    manifest["projects"][0].pop("repositories")
    manifest_path.write_text(yaml.safe_dump(manifest))
    setup = cli("setup", "--path", str(workspace), "--default")
    assert setup["manifest_operation"] == "migrated"
    assert setup["unbound_repositories"] == []
    restored = cli("workspace", "project", "show", "product")
    assert restored["repositories"][0]["id"] == "default"
    assert restored["repositories"][0]["local_path"] == str(local)
    manifest["projects"][0]["local_path"] = str(local)
    manifest_path.write_text(yaml.safe_dump(manifest))
    before = manifest_path.read_bytes()
    with pytest.raises(ConfigurationError):
        WorkspaceManifestRepository().upgrade(workspace)
    assert manifest_path.read_bytes() == before
