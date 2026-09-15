from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from campfire_cli.app.workspace.repository.restructure_repository import (
    SqliteRestructureRepository,
)
from campfire_cli.app.workspace.repository.workspace_repository import (
    SqliteWorkspaceRepository,
)
from campfire_cli.app.workspace.service.adoption_service import AdoptionService
from campfire_cli.common.package_version import InstallMethod
from campfire_cli.main import app

runner = CliRunner()


def write_user_config(workspace: Path, payload: dict) -> Path:
    path = workspace / "_campfire/config.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_short_help_is_available_at_every_command_level() -> None:
    commands = [
        ["-h"],
        ["tree", "-h"],
        ["workspace", "restructure", "-h"],
        ["workspace", "restructure", "inventory", "-h"],
        ["maintenance", "-h"],
        ["maintenance", "check", "-h"],
        ["maintenance", "sync", "-h"],
        ["maintenance", "archive", "-h"],
        ["maintenance", "archive", "check", "-h"],
        ["maintenance", "archive", "apply", "-h"],
        ["skill", "-h"],
        ["base", "-h"],
        ["workspace", "-h"],
        ["workspace", "project", "-h"],
        ["workspace", "project", "adopt", "-h"],
        ["workspace", "project", "create", "-h"],
        ["workspace", "project", "resolve", "-h"],
        ["workspace", "project", "check", "-h"],
        ["workspace", "rebuild", "-h"],
        ["workspace", "space", "-h"],
        ["workspace", "space", "adopt", "-h"],
        ["workspace", "domain", "-h"],
        ["workspace", "domain", "adopt", "-h"],
        ["workspace", "domain", "rename", "-h"],
        ["workspace", "domain", "move", "-h"],
        ["workspace", "domain", "rekey", "-h"],
        ["workspace", "config", "-h"],
        ["workspace", "config", "check", "-h"],
        ["document", "-h"],
        ["document", "profile", "-h"],
        ["document", "profile", "show", "-h"],
        ["document", "type", "-h"],
        ["document", "type", "list", "-h"],
        ["document", "check", "-h"],
        ["document", "inspect", "-h"],
        ["document", "format", "-h"],
        ["document", "apply", "-h"],
        ["document", "move", "-h"],
    ]
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, (command, result.output)
        assert "help" in result.output.lower()


def test_tree_discovers_registered_commands_without_a_parallel_catalog() -> None:
    result = runner.invoke(app, ["tree"])
    assert result.exit_code == 0, result.output
    assert "├── workspace" in result.output
    assert "│   ├── project" in result.output or "│   └── project" in result.output
    assert "├── document" in result.output
    assert "profile" in result.output
    assert "├── maintenance" in result.output
    assert "archive" in result.output
    assert "\n├── project" not in result.output
    assert "\n└── project" not in result.output
    assert "database" not in result.output
    assert "\n│   ├── add" not in result.output
    assert "\n│   ├── attach" not in result.output
    assert "run" not in result.output


def test_project_is_not_exposed_as_a_top_level_command() -> None:
    result = runner.invoke(app, ["project", "-h"])
    assert result.exit_code != 0


def test_removed_compatibility_commands_are_not_registered() -> None:
    commands = [
        ["document", "upsert", "-h"],
        ["workspace", "add", "-h"],
        ["workspace", "attach", "-h"],
        ["workspace", "project", "add", "-h"],
        ["maintenance", "run", "-h"],
        ["maintenance", "plan", "-h"],
        ["maintenance", "show", "-h"],
        ["maintenance", "apply", "-h"],
        ["maintenance", "verify", "-h"],
        ["workspace", "adopt", "-h"],
        ["workspace", "restructure", "domain", "-h"],
        ["update", "-h"],
    ]
    for command in commands:
        assert runner.invoke(app, command).exit_code != 0, command


def test_document_apply_cli_creates_valid_document_without_hidden_sync(workspace: Path) -> None:
    domain_args = [
        "workspace",
        "domain",
        "create",
        "--id",
        "project-example",
        "--name",
        "Example",
        "--path",
        "mywork/【Example】文档中心",
        "--space",
        "work",
        "--type",
        "project-domain",
        "--governance",
        "project-docs",
        "--project",
        "example",
        "--confirm",
    ]
    assert runner.invoke(app, domain_args).exit_code == 0
    body = workspace / "body.md"
    body.write_text("# 发布计划\n", encoding="utf-8")
    relative = "mywork/【Example】文档中心/计划-发布.md"
    result = runner.invoke(
        app,
        [
            "document",
            "apply",
            "--path",
            relative,
            "--type",
            "plan",
            "--set",
            "description=发布计划",
            "--set",
            "lifecycle=proposed",
            "--body-file",
            str(body),
            "--confirm",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "applied"
    assert payload["action"] == "create"
    assert payload["follow_up"] == [
        {
            "command": "maintenance sync",
            "workspace": "test",
            "scope": "mywork/【Example】文档中心",
        },
    ]
    checked = runner.invoke(app, ["document", "check", "--path", relative])
    assert json.loads(checked.output)["status"] == "ok"


def test_setup_creates_manifest_without_overwriting_user_config(
    tmp_path: Path, monkeypatch
) -> None:
    campfire_home = tmp_path / "campfire-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    existing = campfire_home / "config.yml"
    existing.parent.mkdir(parents=True)
    existing.write_text("version: 1\ngovernance:\n  custom: true\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["setup", "--workspace", str(tmp_path), "--id", "new-workspace", "--default"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "initialized"
    assert yaml.safe_load(existing.read_text(encoding="utf-8"))["governance"]["custom"] is True
    assert not (campfire_home / "workspaces/new-workspace/config").exists()
    assert not (tmp_path / ".campfire").exists()
    assert (tmp_path / ".campfire.yaml").is_file()
    resolved = runner.invoke(app, ["workspace", "resolve", "--workspace", "new-workspace"])
    assert json.loads(resolved.output)["workspace"] == str(tmp_path)


def test_setup_requires_id_when_existing_workspace_has_no_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    workspace = tmp_path / "vault"
    workspace.mkdir()

    result = runner.invoke(app, ["setup", "--workspace", str(workspace)])

    assert result.exit_code == 2
    assert "首次 setup 必须提供 --id" in result.output


def test_manifest_attaches_workspace_on_another_device_and_project_bind_is_local(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "vault"
    domain = workspace / "mywork" / "【Example】文档中心"
    domain.mkdir(parents=True)
    (workspace / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch", "main", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )

    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "device-a"))
    assert (
        runner.invoke(app, ["setup", "--workspace", str(workspace), "--id", "personal"]).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "workspace",
                "project",
                "adopt",
                "--id",
                "example",
                "--workspace",
                "personal",
                "--name",
                "Example",
                "--document-domain",
                "mywork/【Example】文档中心",
                "--local-path",
                str(repository),
            ],
        ).exit_code
        == 0
    )
    manifest = yaml.safe_load((workspace / ".campfire.yaml").read_text(encoding="utf-8"))
    assert manifest["workspace"]["id"] == "personal"
    assert "local_path" not in manifest["projects"][0]

    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "device-b"))
    setup = runner.invoke(app, ["setup", "--workspace", str(workspace), "--default"])
    assert setup.exit_code == 0, setup.output
    payload = json.loads(setup.output)
    assert payload["imported_projects"] == ["example"]
    assert payload["unbound_projects"] == ["example"]
    bound = runner.invoke(
        app,
        ["workspace", "project", "bind", "--id", "example", "--local-path", str(repository)],
    )
    assert bound.exit_code == 0, bound.output
    assert json.loads(bound.output)["project"]["local_path"] == str(repository)
    manifest_after = yaml.safe_load((workspace / ".campfire.yaml").read_text(encoding="utf-8"))
    assert "local_path" not in manifest_after["projects"][0]


def test_multiple_registered_workspaces_can_be_selected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    runner.invoke(app, ["setup", "--workspace", str(left), "--id", "left", "--default"])
    runner.invoke(app, ["setup", "--workspace", str(right), "--id", "right"])
    listed = json.loads(runner.invoke(app, ["workspace", "list"]).output)
    assert listed["default_workspace"] == "left"
    assert set(listed["workspaces"]) == {"left", "right"}
    shown = json.loads(runner.invoke(app, ["workspace", "show", "right"]).output)
    assert shown["workspace"] == str(right)
    runner.invoke(app, ["workspace", "set-default", "right"])
    resolved = json.loads(runner.invoke(app, ["workspace", "resolve"]).output)
    assert resolved["workspace_id"] == "right"


def test_workspace_create_builds_minimal_scaffold_and_database(tmp_path: Path, monkeypatch) -> None:
    campfire_home = tmp_path / "campfire-home"
    target = tmp_path / "new-workspace"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    result = runner.invoke(
        app,
        ["workspace", "create", "--id", "new", "--path", str(target), "--default"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "initialized"
    for relative in payload["created_directories"]:
        assert (target / relative).is_dir()
    assert not (target / ".campfire").exists()
    assert (campfire_home / "campfire.db").is_file()
    assert not (campfire_home / "workspaces/new/db").exists()
    assert (target / "mynote/_空间.md").is_file()
    assert (target / "mywork/_空间.md").is_file()
    repeated = runner.invoke(
        app,
        ["workspace", "create", "--id", "new", "--path", str(target)],
    )
    assert repeated.exit_code != 0


def test_space_and_nested_domain_commands_use_marker_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    root = tmp_path / "workspace"
    created = runner.invoke(
        app, ["workspace", "create", "--id", "test", "--path", str(root), "--default"]
    )
    assert created.exit_code == 0, created.output
    spaces = json.loads(runner.invoke(app, ["workspace", "space", "list"]).output)
    assert {item["id"] for item in spaces["spaces"]} == {"knowledge", "work"}

    root_args = [
        "workspace",
        "domain",
        "create",
        "--id",
        "software",
        "--name",
        "软件开发",
        "--path",
        "mynote/软件开发",
        "--space",
        "knowledge",
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-docs",
    ]
    assert json.loads(runner.invoke(app, root_args).output)["status"] == "planned"
    assert runner.invoke(app, [*root_args, "--confirm"]).exit_code == 0
    child_args = [
        "workspace",
        "domain",
        "create",
        "--id",
        "python",
        "--name",
        "Python",
        "--path",
        "mynote/软件开发/Python",
        "--space",
        "knowledge",
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-docs",
        "--parent",
        "software",
        "--confirm",
    ]
    assert runner.invoke(app, child_args).exit_code == 0
    checked = json.loads(runner.invoke(app, ["workspace", "domain", "check"]).output)
    assert checked["status"] == "ok"
    assert {item["id"] for item in checked["domains"]} == {"software", "python"}

    scoped_space = json.loads(
        runner.invoke(app, ["workspace", "space", "check", "--space", "knowledge"]).output
    )
    assert scoped_space["status"] == "ok"
    assert [item["id"] for item in scoped_space["spaces"]] == ["knowledge"]


def test_domain_adopt_declares_existing_directory_without_moving_content(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    root = tmp_path / "workspace"
    created = runner.invoke(
        app, ["workspace", "create", "--id", "test", "--path", str(root), "--default"]
    )
    assert created.exit_code == 0, created.output
    existing = root / "mywork" / "会议记录"
    existing.mkdir()
    note = existing / "会议-示例.md"
    note.write_text("# 示例会议\n", encoding="utf-8")
    args = [
        "workspace",
        "domain",
        "adopt",
        "--id",
        "work-meetings",
        "--name",
        "会议记录",
        "--source",
        str(existing),
        "--target-path",
        "mywork/会议记录",
        "--space",
        "work",
        "--type",
        "work-domain",
        "--governance",
        "work-docs",
    ]
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    payload = json.loads(preview.output)
    assert payload["status"] == "planned"
    assert not any(item["action"] == "create-directory" for item in payload["operations"])
    assert note.is_file()
    assert not (existing / "_领域.md").exists()

    applied = runner.invoke(app, [*args, "--confirm"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "adopted"
    assert note.read_text(encoding="utf-8") == "# 示例会议\n"
    assert (existing / "_领域.md").is_file()
    assert (existing / "_总览/MOC-会议记录总览.md").is_file()

    repeated = runner.invoke(app, [*args, "--confirm"])
    assert repeated.exit_code != 0


def test_space_adopt_declares_existing_root_directory_without_moving_content(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    root = tmp_path / "workspace"
    created = runner.invoke(
        app, ["workspace", "create", "--id", "test", "--path", str(root), "--default"]
    )
    assert created.exit_code == 0, created.output
    existing = root / "myresearch"
    existing.mkdir()
    note = existing / "随手记录.md"
    note.write_text("# 随手记录\n", encoding="utf-8")
    args = [
        "workspace",
        "space",
        "adopt",
        "--id",
        "research",
        "--name",
        "研究",
        "--path",
        "myresearch",
        "--type",
        "knowledge",
    ]
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    payload = json.loads(preview.output)
    assert payload["status"] == "planned"
    assert not any(item["action"] == "create-directory" for item in payload["operations"])

    applied = runner.invoke(app, [*args, "--confirm"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "adopted"
    assert note.read_text(encoding="utf-8") == "# 随手记录\n"
    assert (existing / "_空间.md").is_file()


def test_workspace_config_check_validates_effective_contracts(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "campfire-home"
    root = tmp_path / "workspace"
    monkeypatch.setenv("CAMPFIRE_HOME", str(home))
    created = runner.invoke(
        app, ["workspace", "create", "--id", "test", "--path", str(root), "--default"]
    )
    assert created.exit_code == 0, created.output
    checked = runner.invoke(app, ["workspace", "config", "check"])
    assert checked.exit_code == 0, checked.output
    checked_payload = json.loads(checked.output)
    assert checked_payload["status"] == "ok"

    path = home / "config.yml"
    path.write_text(
        "version: 1\ndocument_types:\n  types:\n    record:\n      prefix: 问题-\n",
        encoding="utf-8",
    )
    invalid = runner.invoke(app, ["workspace", "config", "check"])
    assert invalid.exit_code == 0, invalid.output
    payload = json.loads(invalid.output)
    assert payload["status"] == "issues-found"
    assert any(item["code"] == "duplicate-value" for item in payload["issues"])

    path.write_text(
        "version: 1\nfrontmatter_schema:\n  profiles:\n    task:\n"
        "      value_types:\n        requires_human: number\n",
        encoding="utf-8",
    )
    invalid_types = runner.invoke(app, ["workspace", "config", "check"])
    type_payload = json.loads(invalid_types.output)
    assert any(item["code"] == "invalid-value-types" for item in type_payload["issues"])


def test_project_registry_and_json_transfer(tmp_path: Path, monkeypatch) -> None:
    campfire_home = tmp_path / "campfire-home"
    workspace = tmp_path / "workspace"
    domain = workspace / "mywork" / "【Example】文档中心"
    repository = tmp_path / "repository"
    domain.mkdir(parents=True)
    (workspace / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    repository.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch", "main", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    added_workspace = runner.invoke(
        app, ["setup", "--workspace", str(workspace), "--id", "personal", "--default"]
    )
    assert added_workspace.exit_code == 0, added_workspace.output
    added = runner.invoke(
        app,
        [
            "workspace",
            "project",
            "adopt",
            "--id",
            "example",
            "--workspace",
            "personal",
            "--name",
            "Example",
            "--document-domain",
            "mywork/【Example】文档中心",
            "--local-path",
            str(repository),
            "--git-remote-url",
            "git@example.com:example/repository.git",
            "--default-branch",
            "main",
        ],
    )
    assert added.exit_code == 0, added.output
    payload = json.loads(added.output)
    assert payload["operation"] == "created"
    assert payload["local_path"] == str(repository)
    listed = json.loads(runner.invoke(app, ["workspace", "project", "list"]).output)
    assert [item["id"] for item in listed["projects"]] == ["example"]
    shown = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert shown["document_domain"] == "mywork/【Example】文档中心"
    resolved = json.loads(
        runner.invoke(
            app,
            ["workspace", "project", "resolve", "--path", str(repository)],
        ).output
    )
    assert resolved["status"] == "matched"
    assert resolved["matches"][0]["project"]["id"] == "example"
    assert resolved["matches"][0]["match_basis"] == ["local-path"]
    checked = json.loads(runner.invoke(app, ["workspace", "project", "check", "example"]).output)
    assert checked["status"] == "ok"
    assert checked["observed"]["document_domain_exists"] is True
    assert checked["observed"]["default_branch"] == "main"

    backup = tmp_path / "registry.json"
    exported = runner.invoke(app, ["workspace", "export", "--output", str(backup)])
    assert json.loads(exported.output)["project_count"] == 1
    preview = runner.invoke(app, ["workspace", "import", "--input", str(backup)])
    assert json.loads(preview.output)["status"] == "planned"
    applied = runner.invoke(app, ["workspace", "import", "--input", str(backup), "--confirm"])
    assert json.loads(applied.output)["status"] == "imported"
    assert not (campfire_home / "registry.json").exists()


def test_project_create_previews_then_initializes_document_domain(
    tmp_path: Path, monkeypatch
) -> None:
    campfire_home = tmp_path / "campfire-home"
    workspace = tmp_path / "workspace"
    repository = tmp_path / "new-project"
    workspace.mkdir()
    (workspace / "mywork").mkdir()
    (workspace / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    repository.mkdir()
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    added = runner.invoke(
        app, ["setup", "--workspace", str(workspace), "--id", "personal", "--default"]
    )
    assert added.exit_code == 0, added.output
    arguments = [
        "workspace",
        "project",
        "create",
        "--id",
        "new-project",
        "--workspace",
        "personal",
        "--name",
        "New Project",
        "--document-domain",
        "mywork/【New Project】文档中心",
        "--local-path",
        str(repository),
    ]
    preview = runner.invoke(app, arguments)
    payload = json.loads(preview.output)
    assert payload["status"] == "planned"
    domain = workspace / "mywork/【New Project】文档中心"
    assert not domain.exists()
    assert json.loads(runner.invoke(app, ["workspace", "project", "list"]).output)["projects"] == []

    applied = runner.invoke(app, [*arguments, "--confirm"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "created"
    assert (domain / "_领域.md").is_file()
    assert (domain / "_总览/MOC-New Project总览.md").is_file()
    moc_check = runner.invoke(
        app,
        [
            "--workspace",
            "personal",
            "document",
            "check",
            "--path",
            "mywork/【New Project】文档中心/_总览/MOC-New Project总览.md",
        ],
    )
    assert json.loads(moc_check.output)["status"] == "ok"
    checked = runner.invoke(app, ["workspace", "project", "check", "new-project"])
    checked_payload = json.loads(checked.output)
    assert checked_payload["status"] == "ok"


def test_unified_database_isolates_document_state_by_workspace(tmp_path: Path, monkeypatch) -> None:
    campfire_home = tmp_path / "campfire-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    for workspace_id in ("left", "right"):
        root = tmp_path / workspace_id
        root.mkdir()
        added = runner.invoke(app, ["setup", "--workspace", str(root), "--id", workspace_id])
        assert added.exit_code == 0, added.output
        note = root / "mynote" / "知识-相同路径.md"
        note.parent.mkdir()
        (root / "mynote/_空间.md").write_text(
            "---\nname: 知识\nspace_id: knowledge\nspace_type: knowledge\nstatus: active\n---\n",
            encoding="utf-8",
        )
        note.write_text(
            "---\nname: 相同路径\ndescription: test\ntype: knowledge\n"
            "status: current\ncreated: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n",
            encoding="utf-8",
        )
        checked = runner.invoke(app, ["--workspace", workspace_id, "maintenance", "check"])
        assert checked.exit_code == 0, checked.output

    import sqlite3

    with sqlite3.connect(campfire_home / "campfire.db") as connection:
        rows = connection.execute(
            "SELECT workspace_id, path FROM documents ORDER BY workspace_id"
        ).fetchall()
    assert rows == [
        ("left", "mynote/知识-相同路径.md"),
        ("right", "mynote/知识-相同路径.md"),
    ]


def test_base_sync_is_idempotent_and_preserves_unknown_base(workspace: Path) -> None:
    target = workspace / "治理视图"
    target.mkdir()
    custom = target / "我的视图.base"
    custom.write_text("views: []\n", encoding="utf-8")
    preview = runner.invoke(app, ["--workspace", str(workspace), "base", "sync", "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert len(json.loads(preview.output)["operations"]) == 5
    applied = runner.invoke(app, ["--workspace", str(workspace), "base", "sync"])
    assert applied.exit_code == 0, applied.output
    assert custom.read_text(encoding="utf-8") == "views: []\n"
    assert len(list(target.glob("*.base"))) == 6
    managed = target / "任务工作台.base"
    managed.write_text(
        yaml.safe_dump(yaml.safe_load(managed.read_text(encoding="utf-8")), allow_unicode=True),
        encoding="utf-8",
    )
    repeated = runner.invoke(app, ["--workspace", str(workspace), "base", "sync", "--dry-run"])
    assert json.loads(repeated.output)["operations"] == []
    checked = runner.invoke(app, ["--workspace", str(workspace), "base", "check"])
    assert json.loads(checked.output)["status"] == "ok"


def test_skill_sync_uses_packaged_ssot_and_is_idempotent(workspace: Path) -> None:
    preview = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync", "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["operations"]
    applied = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync"])
    assert applied.exit_code == 0, applied.output
    assert (workspace / "_global_skills/campfire-workspace-maintenance/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-workspace-restructure/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-context-bootstrap/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-conversation-router/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-document-capture/SKILL.md").is_file()
    repeated = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync", "--dry-run"])
    assert json.loads(repeated.output)["operations"] == []
    checked = runner.invoke(app, ["--workspace", str(workspace), "skill", "check"])
    assert json.loads(checked.output)["status"] == "ok"


def test_skill_resolve_routes_inbox_and_knowledge(workspace: Path) -> None:
    for path, expected in (
        ("_收件箱/用户输入/test.md", ["campfire-workspace-maintenance", "campfire-inbox-triage"]),
        ("mynote/【知识】软件开发/test.md", ["campfire-workspace-maintenance"]),
    ):
        result = runner.invoke(
            app, ["--workspace", str(workspace), "skill", "resolve", "--path", path]
        )
        assert result.exit_code == 0, result.output
        names = [item["name"] for item in json.loads(result.output)["skills"]]
        assert names == expected


def test_skill_resolve_routes_project_task(workspace: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "skill",
            "resolve",
            "--path",
            "mywork/【项目】示例/任务/任务-完成联调.md",
        ],
    )
    assert result.exit_code == 0, result.output
    names = [item["name"] for item in json.loads(result.output)["skills"]]
    assert names == [
        "campfire-workspace-maintenance",
    ]


def test_document_profiles_are_compiled_and_resolved(workspace: Path) -> None:
    listed = runner.invoke(app, ["--workspace", str(workspace), "document", "profile", "list"])
    assert listed.exit_code == 0, listed.output
    profiles = json.loads(listed.output)["profiles"]
    assert [profile["name"] for profile in profiles] == [
        "base",
        "knowledge",
        "project-doc",
        "task",
    ]
    task = runner.invoke(
        app,
        ["--workspace", str(workspace), "document", "profile", "show", "task"],
    )
    payload = json.loads(task.output)["profile"]
    assert payload["required"][:3] == ["name", "description", "type"]
    assert "blocked_reason" in payload["optional"]
    assert len(payload["field_order"]) == len(payload["allowed"])

    note = workspace / "mynote/知识-Profile.md"
    note.write_text(
        "---\nname: Profile\ndescription: test\ntype: knowledge\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n",
        encoding="utf-8",
    )
    resolved = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "profile",
            "resolve",
            "--path",
            "mynote/知识-Profile.md",
        ],
    )
    assert json.loads(resolved.output)["profile"]["name"] == "knowledge"


def test_document_profile_list_reads_effective_user_config(workspace: Path) -> None:
    path = write_user_config(
        workspace,
        {
            "version": 1,
            "frontmatter_schema": {
                "profiles": {"custom": {"field_order": [], "required": [], "optional": []}}
            },
        },
    )
    result = runner.invoke(app, ["--workspace", str(workspace), "document", "profile", "list"])
    assert result.exit_code == 0, result.output
    assert "custom" in {item["name"] for item in json.loads(result.output)["profiles"]}
    assert (
        "custom"
        in yaml.safe_load(path.read_text(encoding="utf-8"))["frontmatter_schema"]["profiles"]
    )


def test_document_type_list_reads_effective_user_config(workspace: Path) -> None:
    path = write_user_config(
        workspace,
        {
            "version": 1,
            "document_types": {"types": {"custom": {"prefix": "自定义-", "label": "自定义"}}},
        },
    )

    result = runner.invoke(app, ["--workspace", str(workspace), "document", "type", "list"])
    assert result.exit_code == 0, result.output
    assert "custom" in {item["name"] for item in json.loads(result.output)["types"]}
    configured = yaml.safe_load(path.read_text(encoding="utf-8"))["document_types"]["types"]
    assert "custom" in configured


def test_single_document_check_and_format_require_confirmation(workspace: Path) -> None:
    note = workspace / "mynote/知识-单篇治理.md"
    original = (
        "---\ntype: knowledge\nname: 单篇治理\ndescription: test\nstatus: current\n"
        "created: 2026-09-12\nupdated: 2026-09-12\ntags: []\n---\n# 单篇治理\n"
    )
    note.write_text(original, encoding="utf-8")
    checked = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "check",
            "--path",
            "mynote/知识-单篇治理.md",
        ],
    )
    checked_payload = json.loads(checked.output)
    assert checked_payload["status"] == "needs-review"
    assert checked_payload["issues"][0]["code"] == "frontmatter-field-order-invalid"

    preview = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "format",
            "--path",
            "mynote/知识-单篇治理.md",
        ],
    )
    assert json.loads(preview.output)["status"] == "planned"
    assert note.read_text(encoding="utf-8") == original

    applied = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "format",
            "--path",
            "mynote/知识-单篇治理.md",
            "--confirm",
        ],
    )
    assert json.loads(applied.output)["status"] == "formatted"
    assert note.read_text(encoding="utf-8").startswith("---\nname: 单篇治理\n")
    checked_after = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "check",
            "--path",
            "mynote/知识-单篇治理.md",
        ],
    )
    assert json.loads(checked_after.output)["status"] == "ok"


def test_maintenance_check_creates_sqlite_current_state(workspace: Path) -> None:
    note = workspace / "mynote" / "知识-Test.md"
    note.write_text(
        "---\nname: Test\ndescription: test\ntype: knowledge\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# Test\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "check"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "ok"
    state = workspace / "_campfire/workspaces/test"
    assert (workspace / "_campfire/campfire.db").is_file()
    assert not (state / "db").exists()
    assert (state / "reports/current.json").is_file()
    assert (state / "reports/current.md").is_file()


def test_maintenance_check_validates_task_business_rules(workspace: Path) -> None:
    write_user_config(
        workspace,
        {
            "version": 1,
            "frontmatter_schema": {
                "profiles": {"task": {"enums": {"lifecycle": ["blocked", "completed"]}}}
            },
        },
    )
    note = workspace / "mywork/任务-跟进事项.md"
    note.write_text(
        "---\nname: 跟进事项\ndescription: test\ntype: task\ntask_id: task-test-001\n"
        "status: current\nlifecycle: blocked\ntask_source: assigned\nsource_channel: im\n"
        "assignee: [agent]\nrequires_human: true\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
        "tags: []\n---\n# 跟进事项\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "check"])
    payload = json.loads(result.output)
    missing = {
        issue["field"]
        for issue in payload["issues"]
        if issue["code"] == "frontmatter-field-missing"
    }
    assert "requested_by" not in missing
    assert "blocked_reason" in missing


def test_restructure_plan_is_unapproved_and_hash_change_blocks_apply(workspace: Path) -> None:
    note = workspace / "mynote" / "知识-【Test】标题.md"
    note.write_text(
        "---\nname: 标题\ndescription: test\ntype: knowledge\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# 标题\n",
        encoding="utf-8",
    )
    assert (
        runner.invoke(
            app,
            [
                "--workspace",
                str(workspace),
                "workspace",
                "restructure",
                "inventory",
                "--scope",
                "mynote",
                "--batch",
                "b1",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["--workspace", str(workspace), "workspace", "restructure", "plan", "--batch", "b1"],
        ).exit_code
        == 0
    )
    plan_path = workspace / "_campfire/workspaces/test/batches/b1/plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["items"] and plan["items"][0]["approved"] is False
    plan["items"][0]["approved"] = True
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    note.write_text(note.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "apply",
            "--batch",
            "b1",
            "--confirm",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "blocked"
    assert "source-hash-changed" in result.output


def test_restructure_plan_spec_supports_cross_directory_move_and_metadata(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = workspace / "mynote" / "知识-迁移.md"
    source.write_text(
        "---\nname: 迁移\ndescription: test\ntype: knowledge\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# 迁移\n",
        encoding="utf-8",
    )
    reference = workspace / "mynote" / "知识-引用.md"
    reference.write_text("[迁移](mynote/知识-迁移.md)\n", encoding="utf-8")
    runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "inventory",
            "--scope",
            "mynote",
            "--batch",
            "move",
        ],
    )
    spec = workspace / "move.yaml"
    spec.write_text(
        "operations:\n"
        "  - source: mynote/知识-迁移.md\n"
        "    target: mywork/知识-迁移.md\n"
        "    frontmatter:\n"
        "      status: draft\n"
        "    reason: explicit project move\n"
        "    approved: true\n",
        encoding="utf-8",
    )
    planned = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "plan",
            "--batch",
            "move",
            "--spec",
            str(spec),
        ],
    )
    assert json.loads(planned.output)["item_count"] == 1
    real_save_execution = SqliteRestructureRepository.save_execution

    def fail_execution(_repository, _result) -> None:
        raise OSError("injected execution record failure")

    monkeypatch.setattr(SqliteRestructureRepository, "save_execution", fail_execution)
    failed = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "apply",
            "--batch",
            "move",
            "--confirm",
        ],
    )
    assert failed.exit_code != 0
    assert source.is_file()
    assert not (workspace / "mywork/知识-迁移.md").exists()
    assert "mynote/知识-迁移.md" in reference.read_text(encoding="utf-8")
    monkeypatch.setattr(SqliteRestructureRepository, "save_execution", real_save_execution)
    applied = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "apply",
            "--batch",
            "move",
            "--confirm",
        ],
    )
    applied_payload = json.loads(applied.output)
    assert applied_payload["status"] == "applied", applied.output
    target = workspace / "mywork" / "知识-迁移.md"
    assert target.is_file() and not source.exists()
    assert "status: draft" in target.read_text(encoding="utf-8")
    assert "mywork/知识-迁移.md" in reference.read_text(encoding="utf-8")


def test_restructure_rewrites_unique_wikilink_without_replacing_plain_text(workspace: Path) -> None:
    source = workspace / "mynote/知识-旧标题.md"
    original = "---\ntype: knowledge\n---\n"
    source.write_text(original, encoding="utf-8")
    reference = workspace / "mywork/知识-引用.md"
    reference.write_text("[[知识-旧标题]]\n正文知识-旧标题不应被替换\n", encoding="utf-8")
    runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "inventory",
            "--scope",
            "mynote",
            "--batch",
            "links",
        ],
    )
    spec = workspace / "links.yaml"
    spec.write_text(
        "operations:\n"
        "  - source: mynote/知识-旧标题.md\n"
        "    target: mywork/知识-新标题.md\n"
        "    reason: rename\n"
        "    approved: true\n",
        encoding="utf-8",
    )
    runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "plan",
            "--batch",
            "links",
            "--spec",
            str(spec),
        ],
    )
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "apply",
            "--batch",
            "links",
            "--confirm",
        ],
    )
    assert json.loads(result.output)["status"] == "applied"
    updated = reference.read_text(encoding="utf-8")
    assert "[[知识-新标题]]" in updated
    assert "正文知识-旧标题不应被替换" in updated
    assert (workspace / "mywork/知识-新标题.md").read_text(encoding="utf-8") == original
    verified = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "verify",
            "--batch",
            "links",
        ],
    )
    assert json.loads(verified.output)["status"] == "ok"


def test_restructure_spec_rejects_invalid_enum_during_plan(workspace: Path) -> None:
    source = workspace / "mynote/知识-非法状态.md"
    source.write_text("---\ntype: knowledge\nstatus: current\n---\n", encoding="utf-8")
    runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "inventory",
            "--scope",
            "mynote",
            "--batch",
            "enum",
        ],
    )
    spec = workspace / "enum.yaml"
    spec.write_text(
        "operations:\n"
        "  - source: mynote/知识-非法状态.md\n"
        "    frontmatter: {status: not-a-state}\n"
        "    reason: invalid\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "workspace",
            "restructure",
            "plan",
            "--batch",
            "enum",
            "--spec",
            str(spec),
        ],
    )
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert payload["issues"][0]["code"] == "frontmatter-enum-invalid"
    assert payload["issues"][0]["allowed"] == ["draft", "current", "archived"]


def test_maintenance_check_filters_enriches_and_summarizes(workspace: Path) -> None:
    note = workspace / "mynote" / "知识-坏状态.md"
    note.write_text(
        "---\nname: Test\ndescription: test\ntype: knowledge\nstatus: done\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "maintenance",
            "check",
            "--scope",
            "mynote",
            "--code",
            "frontmatter-enum-invalid",
        ],
    )
    payload = json.loads(result.output)
    assert payload["issue_count"] == 1
    assert payload["total_issue_count"] == 1
    assert payload["issues"][0]["allowed"] == ["draft", "current", "archived"]
    assert payload["issues"][0]["suggestion"]
    summary = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "maintenance",
            "check",
            "--code",
            "frontmatter-enum-invalid",
            "--summary",
        ],
    )
    summary_payload = json.loads(summary.output)
    assert summary_payload["issues"] == []
    assert summary_payload["issue_counts"] == {"frontmatter-enum-invalid": 1}


def test_maintenance_discovers_every_declared_space(workspace: Path) -> None:
    blog = workspace / "myblog"
    blog.mkdir()
    (blog / "_空间.md").write_text(
        "---\nname: 创作\nspace_id: blog\nspace_type: content\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (blog / "随手写.md").write_text("缺少 Frontmatter\n", encoding="utf-8")

    result = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "check"])
    payload = json.loads(result.output)

    assert any(
        issue["path"] == "myblog/随手写.md" and issue["code"] == "frontmatter-missing"
        for issue in payload["issues"]
    )


def test_required_field_distinguishes_missing_from_empty(workspace: Path) -> None:
    note = workspace / "mynote/知识-空字段.md"
    note.write_text(
        "---\nname: 空字段\ndescription: \ntype: knowledge\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["--workspace", str(workspace), "document", "inspect", "--path", "mynote/知识-空字段.md"],
    )
    payload = json.loads(result.output)

    assert any(
        issue["code"] == "frontmatter-field-empty" and issue["field"] == "description"
        for issue in payload["issues"]
    )
    assert not any(
        issue["code"] == "frontmatter-field-missing" and issue["field"] == "description"
        for issue in payload["issues"]
    )


def test_document_commands_delegate_workspace_markers(workspace: Path) -> None:
    result = runner.invoke(
        app, ["--workspace", str(workspace), "document", "inspect", "--path", "mynote/_空间.md"]
    )
    payload = json.loads(result.output)

    assert payload["status"] == "not-applicable"
    assert payload["owner_command"] == "workspace space check"
    assert payload["issues"] == []


def test_decision_lifecycle_is_audited_and_projected(workspace: Path) -> None:
    arguments = [
        "--workspace",
        str(workspace),
        "decision",
        "create",
        "--key",
        "maintenance-requested-by",
        "--question",
        "历史任务的交办人是谁？",
        "--context",
        "正文没有记录交办人。",
        "--recommendation",
        "请项目负责人确认。",
        "--option",
        "领导",
        "--option",
        "个人任务",
        "--related-document",
        "mywork/任务-示例.md",
        "--source-type",
        "maintenance",
        "--source-id",
        "run-001",
        "--session-provider",
        "claude-code",
        "--session-id",
        "session-001",
        "--actor",
        "agent",
    ]
    created = runner.invoke(app, arguments)
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    decision_id = payload["decision"]["id"]
    projection = workspace / f"_协作/decisions/pending/Decision-{decision_id}.md"
    assert payload["status"] == "created"
    assert projection.is_file()
    assert "AUTO-GENERATED:CAMPFIRE-DECISION" in projection.read_text(encoding="utf-8")
    projection_check = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "inspect",
            "--path",
            projection.relative_to(workspace).as_posix(),
        ],
    )
    assert json.loads(projection_check.output)["issues"] == []

    refreshed = json.loads(runner.invoke(app, arguments).output)
    assert refreshed["status"] == "refreshed"
    assert refreshed["decision"]["id"] == decision_id
    assert [event["event_type"] for event in refreshed["events"]] == [
        "decision.created",
        "decision.refreshed",
    ]

    pending = json.loads(
        runner.invoke(
            app, ["--workspace", str(workspace), "decision", "list", "--status", "pending"]
        ).output
    )
    assert [item["id"] for item in pending["decisions"]] == [decision_id]

    answered = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "decision",
            "answer",
            decision_id,
            "--answer",
            "这是领导交办任务",
            "--answered-by",
            "shaoyuanhong",
        ],
    )
    assert answered.exit_code == 0, answered.output
    assert json.loads(answered.output)["decision"]["status"] == "answered"
    assert not projection.exists()
    answered_projection = workspace / f"_协作/decisions/answered/Decision-{decision_id}.md"
    assert answered_projection.is_file()

    closed = runner.invoke(
        app,
        ["--workspace", str(workspace), "decision", "close", decision_id, "--actor", "agent"],
    )
    assert closed.exit_code == 0, closed.output
    closed_payload = json.loads(closed.output)
    assert closed_payload["decision"]["status"] == "closed"
    assert not answered_projection.exists()
    assert (workspace / f"_协作/decisions/closed/Decision-{decision_id}.md").is_file()
    assert [event["event_type"] for event in closed_payload["events"]][-2:] == [
        "decision.answered",
        "decision.closed",
    ]


def test_decision_rejects_invalid_transition(workspace: Path) -> None:
    created = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "decision",
            "create",
            "--key",
            "needs-answer",
            "--question",
            "需要确认吗？",
            "--source-type",
            "agent",
        ],
    )
    decision_id = json.loads(created.output)["decision"]["id"]

    closed = runner.invoke(app, ["--workspace", str(workspace), "decision", "close", decision_id])
    assert closed.exit_code != 0
    assert "expected=answered" in closed.output


def test_filtered_check_reports_scope_status_and_workspace_status(workspace: Path) -> None:
    (workspace / "mynote/坏文档.md").write_text("无 frontmatter\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["--workspace", str(workspace), "maintenance", "check", "--code", "template-enum-invalid"],
    )
    payload = json.loads(result.output)
    assert payload["issue_count"] == 0
    assert payload["total_issue_count"] > 0
    assert payload["status"] == "ok"
    assert payload["workspace_status"] == "needs-review"


def test_document_apply_replaces_semantic_maintenance_plan(workspace: Path) -> None:
    domain = workspace / "mynote/Go"
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\nname: Go\ndomain_id: knowledge-go\ndomain_type: knowledge-domain\n"
        "governance: knowledge-docs\nmoc: '[[MOC-Go]]'\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (domain / "MOC-Go.md").write_text("# Go\n", encoding="utf-8")
    source = domain / "知识-临时笔记.md"
    source.write_text("# Go 并发模型\n\n理解 goroutine 与 channel。\n", encoding="utf-8")
    applied = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "apply",
            "--path",
            "mynote/Go/知识-临时笔记.md",
            "--type",
            "knowledge",
            "--set",
            "name=Go 并发模型",
            "--set",
            "description=理解 goroutine 与 channel 的协作模型",
            "--set",
            "status=current",
            "--set",
            "created=2026-09-12",
            "--set",
            "updated=2026-09-12",
            "--set",
            'tags=["go","concurrency"]',
            "--confirm",
        ],
    )
    applied_payload = json.loads(applied.output)
    assert applied_payload["status"] == "applied", applied.output
    assert applied_payload["write_performed"] is True
    assert source.read_text(encoding="utf-8").startswith("---\nname: Go 并发模型\n")

    inspected = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "inspect",
            "--path",
            "mynote/Go/知识-临时笔记.md",
        ],
    )
    inspected_payload = json.loads(inspected.output)
    assert inspected_payload["status"] == "ok"
    assert inspected_payload["type"] == "knowledge"
    assert inspected_payload["profile"]["name"] == "knowledge"


def test_maintenance_check_validates_skill_template_enums(workspace: Path) -> None:
    write_user_config(
        workspace,
        {
            "version": 1,
            "frontmatter_schema": {
                "profiles": {"task": {"enums": {"lifecycle": ["todo", "completed"]}}}
            },
        },
    )
    template = workspace / "_global_skills" / "task" / "references" / "任务模板.md"
    template.parent.mkdir(parents=True)
    template.write_text("---\ntype: task\nlifecycle: proposed\n---\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["--workspace", str(workspace), "maintenance", "check", "--code", "template-enum-invalid"],
    )
    payload = json.loads(result.output)
    assert payload["issue_count"] == 1
    assert payload["issues"][0]["actual"] == "proposed"


def _create_domain(
    workspace: Path,
    name: str,
    *,
    create_moc: bool = True,
    domain_id: str | None = None,
) -> Path:
    domain = workspace / "mywork" / name
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"domain_id: {domain_id or name.lower()}\n"
        "domain_type: project-domain\n"
        "governance: project-docs\n"
        f'moc: "[[MOC-{name}]]"\n'
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    if create_moc:
        (domain / f"MOC-{name}.md").write_text(
            "# MOC\n\n"
            "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
            "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n",
            encoding="utf-8",
        )
    return domain


def test_sync_reports_bad_metadata_without_blocking_generated_views(workspace: Path) -> None:
    (workspace / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    domain = _create_domain(workspace, "Project")
    (domain / "需求-旧文档.md").write_text("# 缺少元数据\n", encoding="utf-8")

    synced = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "sync"])
    assert synced.exit_code == 0, synced.output
    result = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "check"])

    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["status"] == "needs-review"
    assert payload["write_performed"] is False
    assert "frontmatter-missing" in payload["issue_counts"]
    assert "需求-旧文档" in (domain / "MOC-Project.md").read_text(encoding="utf-8")


def test_scoped_sync_ignores_structural_issue_outside_scope(workspace: Path) -> None:
    (workspace / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    healthy = _create_domain(workspace, "Healthy")
    _create_domain(workspace, "Broken", create_moc=False)
    (healthy / "记录-进展.md").write_text("# 进展\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "maintenance",
            "sync",
            "--scope",
            "mywork/Healthy",
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["status"] == "synced"
    assert payload["scope"] == "mywork/Healthy"
    assert payload["write_performed"] is True
    assert "记录-进展" in (healthy / "MOC-Healthy.md").read_text(encoding="utf-8")


def test_scoped_sync_refreshes_index_without_scanning_unrelated_documents(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    healthy = _create_domain(workspace, "Healthy_A", domain_id="healthy-a")
    unrelated = _create_domain(workspace, "HealthyXA", domain_id="healthy-xa") / "记录-无关.md"
    healthy_note = healthy / "记录-进展.md"
    healthy_note.write_text("# 进展\n", encoding="utf-8")
    unrelated.write_text("# 无关\n", encoding="utf-8")
    runner.invoke(app, ["--workspace", str(workspace), "maintenance", "check"])
    original_read_text = Path.read_text
    reads: list[Path] = []

    def record_read(path: Path, *args, **kwargs):
        reads.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", record_read)
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "maintenance",
            "sync",
            "--scope",
            "mywork/Healthy_A",
        ],
    )

    assert json.loads(result.output)["status"] == "synced", result.output
    assert unrelated not in reads
    with sqlite3.connect(workspace / "_campfire/campfire.db") as connection:
        indexed = connection.execute(
            "select path from documents where workspace_id = 'test' order by path"
        ).fetchall()
    assert ("mywork/Healthy_A/记录-进展.md",) in indexed
    assert ("mywork/HealthyXA/记录-无关.md",) in indexed


def test_archive_scope_does_not_apply_other_candidates(workspace: Path) -> None:
    first = _create_domain(workspace, "First")
    second = _create_domain(workspace, "Second")
    frontmatter = (
        "---\nname: done\ndescription: done\ntype: issue\nproject: test\n"
        "domain: test\nstatus: current\nlifecycle: completed\nrelated: []\n"
        "archive_requested: true\narchive_reason: completed\ncreated: 2026-01-01\n"
        "updated: 2026-01-01\ntags: []\n---\n# done\n"
    )
    first_doc = first / "问题-first.md"
    second_doc = second / "问题-second.md"
    first_doc.write_text(frontmatter, encoding="utf-8")
    second_doc.write_text(frontmatter, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "maintenance",
            "archive",
            "apply",
            "--scope",
            "mywork/First/问题-first.md",
            "--confirm",
        ],
    )

    payload = json.loads(result.output)
    assert payload["status"] == "applied"
    assert payload["changed_document_count"] == 1
    assert payload["write_performed"] is True
    archived = first / "archive/问题-first.md"
    assert archived.is_file()
    archived_text = archived.read_text(encoding="utf-8")
    assert archived_text.index("archived_at:") < archived_text.index("created:")
    assert second_doc.is_file()


def test_domain_restructure_renames_moves_and_rekeys_with_project_metadata(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = workspace / "mywork/【Old】文档中心"
    child = root / "Child"
    child.mkdir(parents=True)
    (root / "_领域.md").write_text(
        "---\nname: Old\ndomain_id: project-old\ndomain_type: project-domain\n"
        "governance: project-docs\nmoc: '[[MOC-Old]]'\nproject_id: example\n"
        "status: active\n---\n\n# Old\n\n原有领域说明。\n",
        encoding="utf-8",
    )
    moc_body = (
        "# MOC\n\n<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n"
    )
    (root / "MOC-Old.md").write_text(moc_body, encoding="utf-8")
    (child / "_领域.md").write_text(
        "---\nname: Child\ndomain_id: project-old-child\n"
        "domain_type: project-domain\ngovernance: project-docs\n"
        "moc: '[[MOC-Child]]'\nparent_domain: project-old\nproject_id: example\n"
        "status: active\n---\n\n# Child\n",
        encoding="utf-8",
    )
    (child / "MOC-Child.md").write_text(moc_body, encoding="utf-8")
    (workspace / ".campfire.yaml").write_text(
        "schema_version: 1\nworkspace:\n  id: test\n  name: Test\n"
        "  governance_version: 1\nprojects: []\n",
        encoding="utf-8",
    )
    added = runner.invoke(
        app,
        [
            "workspace",
            "project",
            "adopt",
            "--id",
            "example",
            "--workspace",
            "test",
            "--name",
            "Old Project",
            "--document-domain",
            "mywork/【Old】文档中心",
        ],
    )
    assert added.exit_code == 0, added.output

    command = [
        "workspace",
        "domain",
        "rename",
        "--domain",
        "project-old",
        "--name",
        "New",
        "--rename-directory",
        "--project-name",
        "New Project",
    ]
    preview = runner.invoke(app, command)
    assert json.loads(preview.output)["status"] == "planned"
    assert root.is_dir()
    real_save_projects = SqliteWorkspaceRepository.save_projects
    calls = 0

    def fail_once(repository, projects) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected project registry failure")
        real_save_projects(repository, projects)

    monkeypatch.setattr(SqliteWorkspaceRepository, "save_projects", fail_once)
    failed = runner.invoke(app, [*command, "--confirm"])
    assert failed.exit_code != 0
    assert root.is_dir()
    assert not (workspace / "mywork/【New】文档中心").exists()
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["name"] == "Old Project"
    assert project["document_domain"] == "mywork/【Old】文档中心"
    monkeypatch.setattr(SqliteWorkspaceRepository, "save_projects", real_save_projects)
    applied = runner.invoke(app, [*command, "--confirm"])
    assert applied.exit_code == 0, applied.output
    applied_payload = json.loads(applied.output)
    assert applied_payload["follow_up"] == [
        {
            "command": "maintenance sync",
            "workspace": "test",
            "scope": "mywork",
        },
    ]
    renamed = workspace / "mywork/【New】文档中心"
    assert renamed.is_dir() and not root.exists()
    assert parse_yaml_frontmatter(renamed / "_领域.md")["domain_id"] == "project-old"
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["name"] == "New Project"
    assert project["document_domain"] == "mywork/【New】文档中心"

    rekeyed = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "rekey",
            "--domain",
            "project-old",
            "--new-id",
            "project-new",
            "--confirm",
        ],
    )
    assert rekeyed.exit_code == 0, rekeyed.output
    assert parse_yaml_frontmatter(renamed / "_领域.md")["domain_id"] == "project-new"
    assert parse_yaml_frontmatter(renamed / "Child/_领域.md")["parent_domain"] == "project-new"

    moved = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "move",
            "--domain",
            "project-new",
            "--target-path",
            "mywork/Moved",
            "--confirm",
        ],
    )
    assert moved.exit_code == 0, moved.output
    assert (workspace / "mywork/Moved/_领域.md").is_file()
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["document_domain"] == "mywork/Moved"


def parse_yaml_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


def test_workspace_rebuild_indexes_spaces_and_domains_from_markers(workspace: Path) -> None:
    import sqlite3

    domain = _create_domain(workspace, "Indexed")
    preview = runner.invoke(app, ["workspace", "rebuild"])
    assert json.loads(preview.output)["status"] == "ready"

    rebuilt = runner.invoke(app, ["workspace", "rebuild", "--confirm"])
    assert rebuilt.exit_code == 0, rebuilt.output
    payload = json.loads(rebuilt.output)
    assert payload["space_count"] == 2
    assert payload["domain_count"] == 1
    database = workspace / "_campfire/campfire.db"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "select space_id from spaces where workspace_id = 'test' order by space_id"
        ).fetchall() == [("knowledge",), ("work",)]
        assert connection.execute(
            "select domain_id, path from domains where workspace_id = 'test'"
        ).fetchall() == [("indexed", "mywork/Indexed")]

    (domain / "_领域.md").unlink()
    runner.invoke(app, ["workspace", "rebuild", "--confirm"])
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "select count(*) from domains where workspace_id = 'test'"
        ).fetchone() == (0,)


def test_external_folder_adoption_stages_applies_and_preserves_source(workspace: Path) -> None:
    source = workspace.parent / "external-notes"
    (source / "assets").mkdir(parents=True)
    (source / "知识-并发.md").write_text("# Go 并发\n", encoding="utf-8")
    (source / "assets/diagram.txt").write_text("diagram\n", encoding="utf-8")

    command = [
        "workspace",
        "domain",
        "adopt",
        "--source",
        str(source),
        "--target-path",
        "mynote/Go并发",
        "--id",
        "knowledge-go-concurrency",
        "--name",
        "Go并发",
        "--space",
        "knowledge",
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-docs",
    ]
    preview = runner.invoke(app, command)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["status"] == "planned"
    assert not (workspace / "mynote/Go并发").exists()

    applied = runner.invoke(app, [*command, "--confirm"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["follow_up"] == [
        {
            "command": "maintenance sync",
            "workspace": "test",
            "scope": "mynote/Go并发",
        },
    ]
    target = workspace / "mynote/Go并发"
    assert (target / "_领域.md").is_file()
    assert (target / "知识-并发.md").is_file()
    assert source.is_dir() and (source / "知识-并发.md").is_file()
    assert not list((workspace / "_收件箱/待接管").glob(".adopt-*"))


def test_internal_folder_adoption_is_applied_in_place(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = workspace / "mynote/LooseNotes"
    source.mkdir(parents=True)
    note = source / "知识-原地接管.md"
    note.write_text("# 原地接管\n", encoding="utf-8")

    command = [
        "workspace",
        "domain",
        "adopt",
        "--source",
        str(source),
        "--target-path",
        "mynote/LooseNotes",
        "--id",
        "knowledge-loose-notes",
        "--name",
        "零散笔记",
        "--space",
        "knowledge",
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-docs",
    ]
    preview = runner.invoke(app, command)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["source_kind"] == "internal"
    assert json.loads(preview.output)["status"] == "planned"
    assert note.is_file()

    real_verify = AdoptionService._verify_files

    def fail_after_write(root: Path, inventory) -> list[dict[str, str]]:
        if root == source:
            return [{"code": "injected-verification-failure", "path": str(root)}]
        return real_verify(root, inventory)

    monkeypatch.setattr(AdoptionService, "_verify_files", staticmethod(fail_after_write))
    failed = runner.invoke(app, [*command, "--confirm"])
    assert failed.exit_code != 0
    assert note.is_file()
    assert not (source / "_领域.md").exists()
    assert not (source / "_总览/MOC-零散笔记总览.md").exists()
    monkeypatch.setattr(AdoptionService, "_verify_files", staticmethod(real_verify))

    applied = runner.invoke(app, [*command, "--confirm"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "adopted"
    assert note.is_file()
    assert (source / "_领域.md").is_file()
    assert (source / "_总览/MOC-零散笔记总览.md").is_file()


def test_adoption_blocks_symbolic_links(workspace: Path) -> None:
    source = workspace.parent / "linked-notes"
    source.mkdir()
    target = workspace.parent / "outside.md"
    target.write_text("outside\n", encoding="utf-8")
    try:
        (source / "linked.md").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"当前环境无法创建符号链接（Windows 需开发者模式或管理员权限）：{exc}")
    result = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "adopt",
            "--source",
            str(source),
            "--target-path",
            "mynote/Linked",
            "--id",
            "knowledge-linked",
            "--name",
            "链接",
            "--space",
            "knowledge",
            "--type",
            "knowledge-domain",
            "--governance",
            "knowledge-docs",
            "--confirm",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert payload["issues"][0]["code"] == "adoption-symlink"


def test_sync_does_not_flag_crlf_generated_file_as_concurrent_change(
    workspace: Path,
) -> None:
    domain = workspace / "mynote" / "知识领域"
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\n"
        "name: 知识领域\n"
        "domain_id: knowledge-domain\n"
        "domain_type: knowledge-domain\n"
        "governance: knowledge-docs\n"
        'moc: "[[MOC-知识领域]]"\n'
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    (domain / "MOC-知识领域.md").write_text(
        "# MOC\n\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n",
        encoding="utf-8",
    )
    (domain / "知识-条目.md").write_text("# 条目\n", encoding="utf-8")

    first = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "sync"])
    assert first.exit_code == 0, first.output
    assert json.loads(first.output)["status"] == "synced", first.output

    relation_page = domain / "generated" / "相关文档-知识领域.md"
    assert relation_page.is_file()
    # 模拟旧版本在 Windows 上写出的 CRLF 生成文件
    relation_page.write_bytes(
        relation_page.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    second = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "sync"])
    assert second.exit_code == 0, second.output
    payload = json.loads(second.output)
    assert payload["status"] == "synced", second.output
    assert payload["issue_counts"].get("concurrent-change") is None


def test_skill_commands_work_without_registered_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "fresh-home"))
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(tmp_path / "skills"))
    listing = runner.invoke(app, ["skill", "list"])
    assert listing.exit_code == 0, listing.output
    payload = json.loads(listing.output)
    assert payload["status"] == "ok"
    assert payload["skills"]

    preview = runner.invoke(app, ["skill", "sync", "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["status"] == "dry-run"


def test_skill_sync_rewrites_crlf_target_without_concurrent_change(
    workspace: Path,
) -> None:
    applied = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync"])
    assert applied.exit_code == 0, applied.output

    target = next((workspace / "_global_skills").glob("campfire-document-capture/SKILL.md"))
    stale = target.read_text(encoding="utf-8") + "\n<!-- 旧版本残留 -->\n"
    target.write_bytes(stale.replace("\n", "\r\n").encode("utf-8"))

    result = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "synced", result.output
    assert "旧版本残留" not in target.read_text(encoding="utf-8")


def test_project_resolve_does_not_match_by_shared_remote_alone(tmp_path: Path, monkeypatch) -> None:
    campfire_home = tmp_path / "campfire-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monorepo = tmp_path / "monorepo"
    sibling_app = monorepo / "apps" / "another-app"
    sibling_app.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch", "main", str(monorepo)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(monorepo),
            "remote",
            "add",
            "origin",
            "git@example.com:team/monorepo.git",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    runner.invoke(app, ["setup", "--workspace", str(workspace), "--id", "personal", "--default"])
    registered_app = monorepo / "apps" / "registered-app"
    registered_app.mkdir(parents=True)
    domain_dir = workspace / "mywork" / "example"
    domain_dir.mkdir(parents=True)
    added = runner.invoke(
        app,
        [
            "workspace",
            "project",
            "adopt",
            "--id",
            "registered-app",
            "--workspace",
            "personal",
            "--name",
            "Registered App",
            "--document-domain",
            "mywork/example",
            "--local-path",
            str(registered_app),
            "--git-remote-url",
            "git@example.com:team/monorepo.git",
        ],
    )
    assert added.exit_code == 0, added.output

    resolved = json.loads(
        runner.invoke(app, ["workspace", "project", "resolve", "--path", str(sibling_app)]).output
    )
    assert resolved["status"] == "unmatched", resolved
    assert resolved["matches"] == []
    assert [item["project"]["id"] for item in resolved["remote_matches"]] == ["registered-app"]
    assert "bind" in resolved["hint"]

    within = json.loads(
        runner.invoke(
            app, ["workspace", "project", "resolve", "--path", str(registered_app)]
        ).output
    )
    assert within["status"] == "matched"
    assert within["matches"][0]["project"]["id"] == "registered-app"


def test_setup_injects_agent_hints_idempotently(workspace: Path, monkeypatch) -> None:
    claude_md = workspace / "CLAUDE.md"
    agents_md = workspace / "AGENTS.md"
    monkeypatch.setenv("CAMPFIRE_AGENT_HINT_PATH", f"{claude_md}{os.pathsep}{agents_md}")
    first = runner.invoke(app, ["setup", "--workspace", str(workspace), "--id", "test"])
    assert first.exit_code == 0, first.output
    payload = json.loads(first.output)
    actions = payload["resources"]["agent_hints"]
    assert {item["action"] for item in actions} == {"created"}
    for item in [claude_md, agents_md]:
        assert "campfire:agent-hints:start" in item.read_text(encoding="utf-8")

    second = runner.invoke(app, ["setup", "--workspace", str(workspace)])
    assert second.exit_code == 0, second.output
    assert {item["action"] for item in json.loads(second.output)["resources"]["agent_hints"]} == {
        "kept"
    }


def test_upgrade_syncs_resources_and_removes_update_alias(workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("campfire_cli.container.fetch_latest_version", lambda _name: None)
    claude_md = workspace / "CLAUDE.md"
    monkeypatch.setenv("CAMPFIRE_AGENT_HINT_PATH", str(claude_md))
    stale = workspace / "_global_skills" / "campfire-document-capture" / "SKILL.md"
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["database"]["status"] == "up-to-date"
    assert payload["skills"]["status"] == "synced"
    assert payload["agent_hints"][0]["action"] == "created"
    assert [item["workspace_id"] for item in payload["workspaces"]] == ["test"]
    assert payload["package"]["action"] == "skipped-offline"
    assert payload["package"]["latest"] is None
    assert stale.is_file()
    stale.write_text("过时内容\n", encoding="utf-8")

    alias = runner.invoke(app, ["update"])
    assert alias.exit_code != 0
    repeated = runner.invoke(app, ["upgrade"])
    assert repeated.exit_code == 0, repeated.output
    upgraded = json.loads(repeated.output)
    assert upgraded["skills"]["status"] == "synced"
    assert upgraded["agent_hints"][0]["action"] == "kept"
    assert stale.read_text(encoding="utf-8") != "过时内容\n"


def test_upgrade_skips_package_update_for_editable_install(workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("campfire_cli.container.fetch_latest_version", lambda _name: "9.9.9")
    monkeypatch.setattr(
        "campfire_cli.container.detect_install_method",
        lambda _name: InstallMethod(manager="editable", update_command=None),
    )
    claude_md = workspace / "CLAUDE.md"
    monkeypatch.setenv("CAMPFIRE_AGENT_HINT_PATH", str(claude_md))
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["package"]["action"] == "skipped-editable"
    assert payload["package"]["update_available"] is True
    assert "editable" in payload["package"]["hint"]
    assert payload["skills"]["status"] == "synced"


def test_upgrade_spawns_detached_updater_for_managed_install(workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("campfire_cli.container.fetch_latest_version", lambda _name: "9.9.9")
    monkeypatch.setattr(
        "campfire_cli.container.detect_install_method",
        lambda _name: InstallMethod(
            manager="uv-tool", update_command=["uv", "tool", "upgrade", "campfire-cli"]
        ),
    )
    monkeypatch.setattr(
        "campfire_cli.container.default_align_command",
        lambda: ["campfire", "upgrade", "--skip-package"],
    )
    spawned: list[tuple[list[str], list[str]]] = []
    monkeypatch.setattr(
        "campfire_cli.container.spawn_detached_updater",
        lambda update, align: spawned.append((update, align)) or "updater-script",
    )
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["package"]["action"] == "updater-spawned"
    assert payload["package"]["update_command"] == ["uv", "tool", "upgrade", "campfire-cli"]
    assert payload["resources"] == "deferred"
    assert "skills" not in payload
    assert spawned == [
        (["uv", "tool", "upgrade", "campfire-cli"], ["campfire", "upgrade", "--skip-package"])
    ]


def test_setup_without_workspace_syncs_global_resources_and_prints_guidance(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(home))
    hint_file = tmp_path / "CLAUDE.md"
    monkeypatch.setenv("CAMPFIRE_AGENT_HINT_PATH", str(hint_file))
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "needs-input"
    commands = {item["command"] for item in payload["paths"]}
    assert "campfire setup --workspace <vault路径> [--id <id>] --default" in commands
    assert any("workspace create" in command for command in commands)
    assert any("upgrade" in command for command in commands)
    assert payload["resources"]["skills"]["status"] == "synced"
    assert {item["action"] for item in payload["resources"]["agent_hints"]} == {"created"}
    assert "campfire:agent-hints:start" in hint_file.read_text(encoding="utf-8")
    assert "manifest" in payload["skipped"]
    assert "health-check" in payload["skipped"]


def test_archive_check_lists_candidates_with_reason_and_related(
    workspace: Path,
) -> None:
    domain = workspace / "mywork" / "【归档测试】文档中心"
    domain.mkdir(parents=True)
    (workspace / "mywork" / "_空间.md").exists()
    (domain / "_领域.md").write_text(
        "---\nname: 归档测试\ndomain_id: archive-test\ndomain_type: project-domain\n"
        'governance: project-docs\nmoc: "[[MOC-归档测试]]"\nstatus: active\n---\n',
        encoding="utf-8",
    )
    (domain / "MOC-归档测试.md").write_text(
        "---\nname: 归档测试总览\ndescription: 测试。\ntype: moc\nstatus: current\n"
        "lifecycle: maintained\ncreated: 2026-09-14\nupdated: 2026-09-14\ntags: []\n---\n"
        "# 归档测试总览\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
        "占位\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n",
        encoding="utf-8",
    )
    (domain / "计划-待归档.md").write_text(
        "---\nname: 待归档\ndescription: 测试\ntype: plan\nproject: archive-test\n"
        "domain: archive-test\n"
        "status: current\nlifecycle: proposed\n"
        'related:\n  - "[[看板-某清单]]"\n'
        "superseded_by: []\narchive_requested: true\narchive_reason: completed\n"
        "created: 2026-09-14\nupdated: 2026-09-14\n---\n# 待归档\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["maintenance", "archive", "check"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    candidates = payload["candidates"]
    assert ["mywork/【归档测试】文档中心/计划-待归档.md".replace("/", os.sep)] == [
        item["source"] for item in candidates
    ]
    assert candidates[0]["archive_reason"] == "completed"
    assert candidates[0]["related"] == ["[[看板-某清单]]"]


def test_document_kanban_check_validates_renderability_contract(workspace: Path) -> None:
    domain = workspace / "mywork" / "【看板测试】文档中心"
    domain.mkdir(parents=True)
    plain = domain / "看板-普通清单.md"
    plain.write_text(
        "---\nname: 普通清单\ndescription: 测试。\ntype: board\nstatus: current\n"
        "lifecycle: proposed\ncreated: 2026-09-14\nupdated: 2026-09-14\ntags: []\n---\n"
        "## 看板\n\n### 未排期\n\n- [ ] 事项\n",
        encoding="utf-8",
    )
    rendered = domain / "看板-可渲染.md"
    rendered.write_text(
        "---\nname: 可渲染\ndescription: 测试。\ntype: board\nkanban-plugin: basic\n"
        "status: current\nlifecycle: proposed\ncreated: 2026-09-14\nupdated: 2026-09-14\n"
        "tags: []\n---\n## 未排期\n\n- [ ] 事项\n",
        encoding="utf-8",
    )
    plain_result = runner.invoke(app, ["document", "kanban-check", "--path", str(plain)])
    assert plain_result.exit_code == 0, plain_result.output
    plain_payload = json.loads(plain_result.output)
    assert plain_payload["renderable"] is False
    assert "kanban-plugin-missing" in {item["code"] for item in plain_payload["issues"]}

    rendered_result = runner.invoke(app, ["document", "kanban-check", "--path", str(rendered)])
    assert rendered_result.exit_code == 0, rendered_result.output
    rendered_payload = json.loads(rendered_result.output)
    assert rendered_payload["renderable"] is True
    assert rendered_payload["issues"] == []


def test_skill_sync_installs_kanban_board_skill(workspace: Path) -> None:
    result = runner.invoke(app, ["skill", "sync"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    paths = [item["path"] for item in payload["operations"]]
    assert paths
    kanban_paths = [path for path in paths if "campfire-kanban-board" in path]
    assert kanban_paths
    for path in kanban_paths:
        assert "kanban-plugin" in Path(path).read_text(encoding="utf-8")
