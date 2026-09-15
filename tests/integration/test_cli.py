from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from typer.main import get_command
from typer.testing import CliRunner

from campfire_cli.app.workspace.repository.restructure_repository import (
    SqliteRestructureRepository,
)
from campfire_cli.app.workspace.repository.workspace_repository import (
    SqliteWorkspaceRepository,
)
from campfire_cli.app.workspace.service.adoption_service import AdoptionService
from campfire_cli.common.filesystem import FileChangeExecutor
from campfire_cli.common.package_version import InstallMethod
from campfire_cli.main import app

runner = CliRunner()


def write_user_config(workspace: Path, payload: dict) -> Path:
    path = workspace / "_campfire/config.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def write_domain_marker(
    directory: Path,
    domain_id: str,
    name: str,
    *,
    governance: str = "project-docs",
    project_id: str | None = None,
    parent_domain: str | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    project = f"project_id: {project_id}\n" if project_id else ""
    parent = f"parent_domain: {parent_domain}\n" if parent_domain else ""
    (directory / "_领域.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"domain_id: {domain_id}\n"
        "domain_type: project-domain\n"
        f"governance: {governance}\n"
        f"moc: '[[MOC-{name}]]'\n"
        f"{parent}"
        f"{project}"
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    (directory / f"MOC-{name}.md").write_text(
        "# MOC\n\n<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n",
        encoding="utf-8",
    )


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
        ["workspace", "domain", "merge", "-h"],
        ["workspace", "domain", "delete", "-h"],
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


def test_golden_path_help_is_complete_at_narrow_terminal_width() -> None:
    apply_help = runner.invoke(app, ["document", "apply", "-h"], terminal_width=80)
    plan_help = runner.invoke(
        app,
        ["workspace", "restructure", "plan", "-h"],
        terminal_width=80,
    )

    assert apply_help.exit_code == 0, apply_help.output
    assert "文件名可省略类型前缀" in apply_help.output
    assert "同步文件名和引用" in apply_help.output
    assert plan_help.exit_code == 0, plan_help.output
    assert "无 --spec" in plan_help.output
    assert "只规范化类型与文件名" in plan_help.output
    assert "operations spec" in plan_help.output


def test_public_selectors_keep_one_stable_golden_path(workspace: Path) -> None:
    def options(path: tuple[str, ...]) -> set[str]:
        command = get_command(app)
        for name in path:
            command = command.commands[name]
        return {
            option
            for parameter in command.params
            for option in (*parameter.opts, *parameter.secondary_opts)
        }

    assert "--workspace" in options(())

    contracts = {
        ("document", "move"): (
            {"--path", "--domain", "--name"},
            {"--from", "--to", "--target-path"},
        ),
        ("workspace", "project", "adopt"): (
            {"--domain"},
            {"--workspace", "--document-domain"},
        ),
        ("workspace", "domain", "create"): (
            {"--path"},
            {"--space", "--parent"},
        ),
        ("workspace", "domain", "rename"): (
            {"--domain", "--name"},
            {"--target-path", "--rename-directory", "--project-name"},
        ),
        ("workspace", "domain", "move"): (
            {"--domain", "--target"},
            {"--target-path", "--parent-domain"},
        ),
    }
    for command, (required, forbidden) in contracts.items():
        public_options = options(command)
        assert required <= public_options, command
        assert forbidden.isdisjoint(public_options), command

    rejected = runner.invoke(
        app,
        ["--workspace", str(workspace), "workspace", "resolve"],
    )
    assert rejected.exit_code == 2
    assert "Workspace 未注册" in rejected.output


def test_every_public_path_option_has_an_explicit_boundary_classification() -> None:
    classified = {
        ("setup", "--path"): "physical-target",
        ("workspace create", "--path"): "physical-target",
        ("workspace export", "--output"): "file-output",
        ("workspace import", "--input"): "file-input",
        ("workspace project adopt", "--local-path"): "external-path",
        ("workspace project update", "--local-path"): "external-path",
        ("workspace project create", "--path"): "physical-target",
        ("workspace project create", "--local-path"): "external-path",
        ("workspace project resolve", "--path"): "external-path",
        ("workspace project bind", "--local-path"): "external-path",
        ("workspace space create", "--path"): "physical-target",
        ("workspace space adopt", "--path"): "physical-target",
        ("workspace domain create", "--path"): "physical-target",
        ("workspace domain adopt", "--source"): "external-path",
        ("workspace domain adopt", "--target-path"): "physical-target",
        ("workspace restructure inventory", "--scope"): "scope",
        ("workspace restructure plan", "--spec"): "file-input",
        ("document check", "--path"): "document-path",
        ("document kanban-check", "--path"): "document-path",
        ("document inspect", "--path"): "document-path",
        ("document format", "--path"): "document-path",
        ("document apply", "--path"): "document-path",
        ("document apply", "--body-file"): "file-input",
        ("document move", "--path"): "document-path",
        ("document profile resolve", "--path"): "document-path",
        ("decision create", "--related-document"): "document-path",
        ("maintenance check", "--scope"): "scope",
        ("maintenance sync", "--scope"): "scope",
        ("maintenance archive check", "--scope"): "scope",
        ("maintenance archive apply", "--scope"): "scope",
        ("skill resolve", "--path"): "document-path",
    }
    path_flags = {
        "--path",
        "--local-path",
        "--target-path",
        "--scope",
        "--body-file",
        "--spec",
        "--input",
        "--output",
        "--related-document",
    }
    discovered: set[tuple[str, str]] = set()

    def walk(command, parts: tuple[str, ...] = ()) -> None:
        if hasattr(command, "commands"):
            for name, child in command.commands.items():
                walk(child, (*parts, name))
            return
        for parameter in command.params:
            options = getattr(parameter, "opts", [])
            for option in options:
                if option in path_flags or (
                    option == "--source" and "TyperPath" in str(parameter.type)
                ):
                    discovered.add((" ".join(parts), option))

    walk(get_command(app))
    assert discovered == set(classified)
    assert set(classified.values()) == {
        "physical-target",
        "external-path",
        "document-path",
        "scope",
        "file-input",
        "file-output",
    }


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


def test_document_apply_follow_up_normalizes_nested_directory_to_domain(
    workspace: Path,
) -> None:
    domain = workspace / "mywork/Project"
    write_domain_marker(domain, "project", "Project", project_id="example")
    (domain / "任务").mkdir()
    result = runner.invoke(
        app,
        [
            "document",
            "apply",
            "--path",
            "mywork/Project/任务/下一版.md",
            "--type",
            "plan",
            "--set",
            "description=发布计划",
            "--set",
            "lifecycle=proposed",
            "--confirm",
        ],
    )

    payload = json.loads(result.output)
    follow_up = payload["follow_up"][0]
    synced = runner.invoke(
        app,
        [
            "--workspace",
            follow_up["workspace"],
            "maintenance",
            "sync",
            "--scope",
            follow_up["scope"],
        ],
    )
    synced_payload = json.loads(synced.output)

    assert result.exit_code == 0, result.output
    assert payload["target"] == "mywork/Project/任务/计划-下一版.md"
    assert follow_up["scope"] == "mywork/Project"
    assert synced.exit_code == 0, synced.output
    assert synced_payload["status"] == "synced"
    assert synced_payload["domain_count"] == 1
    assert synced_payload["indexed_document_count"] >= 1


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
        ["setup", "--path", str(tmp_path), "--id", "new-workspace", "--default"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "initialized"
    assert yaml.safe_load(existing.read_text(encoding="utf-8"))["governance"]["custom"] is True
    assert not (campfire_home / "workspaces/new-workspace/config").exists()
    assert not (tmp_path / ".campfire").exists()
    assert (tmp_path / ".campfire.yaml").is_file()
    resolved = runner.invoke(app, ["--workspace", "new-workspace", "workspace", "resolve"])
    assert json.loads(resolved.output)["workspace"] == str(tmp_path)


def test_setup_requires_id_when_existing_workspace_has_no_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    workspace = tmp_path / "vault"
    workspace.mkdir()

    result = runner.invoke(app, ["setup", "--path", str(workspace)])

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
    write_domain_marker(domain, "project-example", "Example", project_id="example")
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
        runner.invoke(app, ["setup", "--path", str(workspace), "--id", "personal"]).exit_code == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "--workspace",
                "personal",
                "workspace",
                "project",
                "adopt",
                "--id",
                "example",
                "--name",
                "Example",
                "--domain",
                "project-example",
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
    setup = runner.invoke(app, ["setup", "--path", str(workspace), "--default"])
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
    runner.invoke(app, ["setup", "--path", str(left), "--id", "left", "--default"])
    runner.invoke(app, ["setup", "--path", str(right), "--id", "right"])
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
        "--type",
        "knowledge-domain",
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
    write_domain_marker(domain, "project-example", "Example", project_id="example")
    repository.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch", "main", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    added_workspace = runner.invoke(
        app, ["setup", "--path", str(workspace), "--id", "personal", "--default"]
    )
    assert added_workspace.exit_code == 0, added_workspace.output
    added = runner.invoke(
        app,
        [
            "--workspace",
            "personal",
            "workspace",
            "project",
            "adopt",
            "--id",
            "example",
            "--name",
            "Example",
            "--domain",
            "project-example",
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

    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    registered_other = runner.invoke(
        app,
        ["setup", "--path", str(other_workspace), "--id", "other"],
    )
    assert registered_other.exit_code == 0, registered_other.output
    assert (
        json.loads(
            runner.invoke(app, ["--workspace", "other", "workspace", "project", "list"]).output
        )["projects"]
        == []
    )
    wrong_workspace = runner.invoke(
        app,
        [
            "--workspace",
            "other",
            "workspace",
            "project",
            "update",
            "--id",
            "example",
            "--name",
            "Wrong Workspace",
        ],
    )
    assert wrong_workspace.exit_code == 2
    assert "属于 Workspace personal" in wrong_workspace.output

    updated = runner.invoke(
        app,
        [
            "--workspace",
            "personal",
            "workspace",
            "project",
            "update",
            "--id",
            "example",
            "--git-remote-url",
            "git@example.com:example/renamed.git",
        ],
    )
    updated_payload = json.loads(updated.output)
    assert updated_payload["name"] == "Example"
    assert updated_payload["document_domain"] == "mywork/【Example】文档中心"
    assert updated_payload["local_path"] == str(repository)
    assert updated_payload["default_branch"] == "main"
    assert updated_payload["git_remote_url"] == "git@example.com:example/renamed.git"

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
    added = runner.invoke(app, ["setup", "--path", str(workspace), "--id", "personal", "--default"])
    assert added.exit_code == 0, added.output
    arguments = [
        "--workspace",
        "personal",
        "workspace",
        "project",
        "create",
        "--id",
        "new-project",
        "--name",
        "New Project",
        "--path",
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
        added = runner.invoke(app, ["setup", "--path", str(root), "--id", workspace_id])
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
    preview = runner.invoke(app, ["--workspace", "test", "base", "sync", "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert len(json.loads(preview.output)["operations"]) == 5
    applied = runner.invoke(app, ["--workspace", "test", "base", "sync"])
    assert applied.exit_code == 0, applied.output
    assert custom.read_text(encoding="utf-8") == "views: []\n"
    assert len(list(target.glob("*.base"))) == 6
    managed = target / "任务工作台.base"
    managed.write_text(
        yaml.safe_dump(yaml.safe_load(managed.read_text(encoding="utf-8")), allow_unicode=True),
        encoding="utf-8",
    )
    repeated = runner.invoke(app, ["--workspace", "test", "base", "sync", "--dry-run"])
    assert json.loads(repeated.output)["operations"] == []
    checked = runner.invoke(app, ["--workspace", "test", "base", "check"])
    assert json.loads(checked.output)["status"] == "ok"


def test_skill_sync_uses_packaged_ssot_and_is_idempotent(workspace: Path) -> None:
    preview = runner.invoke(app, ["--workspace", "test", "skill", "sync", "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["operations"]
    applied = runner.invoke(app, ["--workspace", "test", "skill", "sync"])
    assert applied.exit_code == 0, applied.output
    assert (workspace / "_global_skills/campfire-workspace-maintenance/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-workspace-restructure/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-context-bootstrap/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-conversation-router/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-document-capture/SKILL.md").is_file()
    repeated = runner.invoke(app, ["--workspace", "test", "skill", "sync", "--dry-run"])
    assert json.loads(repeated.output)["operations"] == []
    checked = runner.invoke(app, ["--workspace", "test", "skill", "check"])
    assert json.loads(checked.output)["status"] == "ok"


def test_skill_resolve_routes_inbox_and_knowledge(workspace: Path) -> None:
    for path, expected in (
        ("_收件箱/用户输入/test.md", ["campfire-workspace-maintenance", "campfire-inbox-triage"]),
        ("mynote/【知识】软件开发/test.md", ["campfire-workspace-maintenance"]),
    ):
        result = runner.invoke(app, ["--workspace", "test", "skill", "resolve", "--path", path])
        assert result.exit_code == 0, result.output
        names = [item["name"] for item in json.loads(result.output)["skills"]]
        assert names == expected


def test_skill_resolve_routes_project_task(workspace: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--workspace",
            "test",
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
    listed = runner.invoke(app, ["--workspace", "test", "document", "profile", "list"])
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
        ["--workspace", "test", "document", "profile", "show", "task"],
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
            "test",
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
    result = runner.invoke(app, ["--workspace", "test", "document", "profile", "list"])
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

    result = runner.invoke(app, ["--workspace", "test", "document", "type", "list"])
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
            "test",
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
            "test",
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
            "test",
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
            "test",
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
    result = runner.invoke(app, ["--workspace", "test", "maintenance", "check"])
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
    result = runner.invoke(app, ["--workspace", "test", "maintenance", "check"])
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
                "test",
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
    planned = runner.invoke(
        app,
        ["--workspace", "test", "workspace", "restructure", "plan", "--batch", "b1"],
    )
    assert planned.exit_code == 0
    planned_payload = json.loads(planned.output)
    assert planned_payload["inventory_count"] == 1
    assert planned_payload["planned_count"] == 1
    assert planned_payload["approved_count"] == 0
    assert planned_payload["unapproved_count"] == 1
    unapproved = runner.invoke(
        app,
        ["--workspace", "test", "workspace", "restructure", "apply", "--batch", "b1"],
    )
    unapproved_payload = json.loads(unapproved.output)
    assert unapproved_payload["status"] == "needs-review"
    assert unapproved_payload["item_count"] == 1
    assert unapproved_payload["inventory_count"] == 1
    assert unapproved_payload["issues"][0]["code"] == "restructure-items-unapproved"
    assert unapproved_payload["issues"][0]["detail"] == "1"
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
            "test",
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


def test_restructure_plan_reports_up_to_date_when_nothing_is_inferred(workspace: Path) -> None:
    (workspace / "mynote/知识-已规范.md").write_text(
        "---\ntype: knowledge\n---\n# 已规范\n",
        encoding="utf-8",
    )
    runner.invoke(
        app,
        [
            "--workspace",
            "test",
            "workspace",
            "restructure",
            "inventory",
            "--scope",
            "mynote",
            "--batch",
            "already-normalized",
        ],
    )

    result = runner.invoke(
        app,
        [
            "--workspace",
            "test",
            "workspace",
            "restructure",
            "plan",
            "--batch",
            "already-normalized",
        ],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0, result.output
    assert payload["status"] == "up-to-date"
    assert payload["inventory_count"] == 1
    assert payload["planned_count"] == 0


def test_restructure_confirm_never_partially_applies_unapproved_plan(workspace: Path) -> None:
    first = workspace / "mynote/知识-first.md"
    second = workspace / "mynote/知识-second.md"
    first.write_text("---\ntype: knowledge\n---\n", encoding="utf-8")
    second.write_text("---\ntype: knowledge\n---\n", encoding="utf-8")
    runner.invoke(
        app,
        [
            "workspace",
            "restructure",
            "inventory",
            "--scope",
            "mynote",
            "--batch",
            "partial",
        ],
    )
    spec = workspace / "partial.yaml"
    spec.write_text(
        "operations:\n"
        "  - source: mynote/知识-first.md\n"
        "    target: mywork/知识-first.md\n"
        "    approved: true\n"
        "  - source: mynote/知识-second.md\n"
        "    target: mywork/知识-second.md\n",
        encoding="utf-8",
    )
    planned = runner.invoke(
        app,
        ["workspace", "restructure", "plan", "--batch", "partial", "--spec", str(spec)],
    )
    assert json.loads(planned.output)["approved_count"] == 1

    result = runner.invoke(
        app,
        ["workspace", "restructure", "apply", "--batch", "partial", "--confirm"],
    )
    payload = json.loads(result.output)
    assert payload["status"] == "needs-review"
    assert payload["inventory_count"] == 2
    assert payload["approved_count"] == 1
    assert payload["unapproved_count"] == 1
    assert first.is_file() and second.is_file()
    assert not (workspace / "mywork/知识-first.md").exists()


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
            "test",
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
            "test",
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
            "test",
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
            "test",
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
    assert applied_payload["approved_count"] == 1
    assert applied_payload["unapproved_count"] == 0
    assert applied_payload["follow_up"] == [
        {"command": "maintenance sync", "workspace": "test", "scope": "."}
    ]
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
            "test",
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
            "test",
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
            "test",
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
            "test",
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
            "test",
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
            "test",
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


def test_restructure_spec_rejects_unknown_schema_fields_with_json_error(
    workspace: Path,
) -> None:
    source = workspace / "mynote/知识-字段拼错.md"
    source.write_text("---\ntype: knowledge\n---\n", encoding="utf-8")
    runner.invoke(
        app,
        [
            "workspace",
            "restructure",
            "inventory",
            "--scope",
            "mynote",
            "--batch",
            "bad-schema",
        ],
    )
    spec = workspace / "bad-schema.yaml"
    spec.write_text(
        "operations:\n  - source: mynote/知识-字段拼错.md\n    approve: true\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "workspace",
            "restructure",
            "plan",
            "--batch",
            "bad-schema",
            "--spec",
            str(spec),
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert "重构规格无效" in payload["message"]
    assert "approve" in payload["message"]


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
            "test",
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
            "test",
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

    result = runner.invoke(app, ["--workspace", "test", "maintenance", "check"])
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
        ["--workspace", "test", "document", "inspect", "--path", "mynote/知识-空字段.md"],
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
        app, ["--workspace", "test", "document", "inspect", "--path", "mynote/_空间.md"]
    )
    payload = json.loads(result.output)

    assert payload["status"] == "not-applicable"
    assert payload["owner_command"] == "workspace space check"
    assert payload["issues"] == []


def test_decision_lifecycle_is_audited_and_projected(workspace: Path) -> None:
    arguments = [
        "--workspace",
        "test",
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
            "test",
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
            app, ["--workspace", "test", "decision", "list", "--status", "pending"]
        ).output
    )
    assert [item["id"] for item in pending["decisions"]] == [decision_id]

    answered = runner.invoke(
        app,
        [
            "--workspace",
            "test",
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
        ["--workspace", "test", "decision", "close", decision_id, "--actor", "agent"],
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
            "test",
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

    closed = runner.invoke(app, ["--workspace", "test", "decision", "close", decision_id])
    assert closed.exit_code != 0
    assert "expected=answered" in closed.output


def test_filtered_check_reports_scope_status_and_workspace_status(workspace: Path) -> None:
    (workspace / "mynote/坏文档.md").write_text("无 frontmatter\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["--workspace", "test", "maintenance", "check", "--code", "template-enum-invalid"],
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
            "test",
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
            "test",
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
        ["--workspace", "test", "maintenance", "check", "--code", "template-enum-invalid"],
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

    synced = runner.invoke(app, ["--workspace", "test", "maintenance", "sync"])
    assert synced.exit_code == 0, synced.output
    result = runner.invoke(app, ["--workspace", "test", "maintenance", "check"])

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
            "test",
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


def test_scoped_sync_normalizes_domain_internal_path(workspace: Path) -> None:
    domain = _create_domain(workspace, "Project", domain_id="project")
    nested = domain / "任务"
    nested.mkdir()
    (nested / "记录-进展.md").write_text("# 进展\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["maintenance", "sync", "--scope", "mywork/Project/任务"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0, result.output
    assert payload["status"] == "synced"
    assert payload["scope"] == "mywork/Project"
    assert payload["domain_count"] == 1
    assert payload["indexed_document_count"] >= 1


def test_scoped_sync_rejects_existing_unmanaged_directory(workspace: Path) -> None:
    (workspace / "mywork/Loose").mkdir()

    result = runner.invoke(
        app,
        ["maintenance", "sync", "--scope", "mywork/Loose"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0, result.output
    assert payload["status"] == "blocked"
    assert payload["issues"][0]["code"] == "scope-unmanaged"


def test_scoped_sync_rejects_missing_path_inside_domain(workspace: Path) -> None:
    domain = workspace / "mywork/Project"
    write_domain_marker(domain, "project", "Project")

    result = runner.invoke(
        app,
        ["maintenance", "sync", "--scope", "mywork/Project/不存在"],
    )
    payload = json.loads(result.output)

    assert payload["status"] == "blocked"
    assert payload["issues"][0]["code"] == "scope-missing"


def test_scoped_sync_refreshes_index_without_scanning_unrelated_documents(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    healthy = _create_domain(workspace, "Healthy_A", domain_id="healthy-a")
    unrelated = _create_domain(workspace, "HealthyXA", domain_id="healthy-xa") / "记录-无关.md"
    healthy_note = healthy / "记录-进展.md"
    healthy_note.write_text("# 进展\n", encoding="utf-8")
    unrelated.write_text("# 无关\n", encoding="utf-8")
    runner.invoke(app, ["--workspace", "test", "maintenance", "check"])
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
            "test",
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
            "test",
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
            "--workspace",
            "test",
            "workspace",
            "project",
            "adopt",
            "--id",
            "example",
            "--name",
            "Old Project",
            "--domain",
            "project-old",
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
    ]
    preview = runner.invoke(app, command)
    preview_payload = json.loads(preview.output)
    assert preview_payload["status"] == "planned"
    assert preview_payload["follow_up"] == []
    assert root.is_dir()
    applied = runner.invoke(app, [*command, "--confirm"])
    assert applied.exit_code == 0, applied.output
    applied_payload = json.loads(applied.output)
    assert applied_payload["follow_up"] == [
        {
            "command": "maintenance sync",
            "workspace": "test",
            "scope": "mywork/【Old】文档中心",
        },
    ]
    assert root.is_dir()
    assert parse_yaml_frontmatter(root / "_领域.md")["name"] == "New"
    assert parse_yaml_frontmatter(root / "_领域.md")["domain_id"] == "project-old"
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["name"] == "Old Project"
    assert project["document_domain"] == "mywork/【Old】文档中心"

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
    assert parse_yaml_frontmatter(root / "_领域.md")["domain_id"] == "project-new"
    assert parse_yaml_frontmatter(root / "Child/_领域.md")["parent_domain"] == "project-new"

    destination = workspace / "mywork/Destination"
    destination.mkdir()
    (destination / "_领域.md").write_text(
        "---\nname: Destination\ndomain_id: project-destination\n"
        "domain_type: project-domain\ngovernance: project-docs\n"
        "moc: '[[MOC-Destination]]'\nproject_id: example\n"
        "status: active\n---\n\n# Destination\n",
        encoding="utf-8",
    )
    (destination / "MOC-Destination.md").write_text(moc_body, encoding="utf-8")

    move_command = [
        "workspace",
        "domain",
        "move",
        "--domain",
        "project-new",
        "--target",
        "project-destination",
    ]
    real_save_projects = SqliteWorkspaceRepository.save_projects
    calls = 0

    def fail_once(repository, projects) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected project registry failure")
        real_save_projects(repository, projects)

    monkeypatch.setattr(SqliteWorkspaceRepository, "save_projects", fail_once)
    failed = runner.invoke(app, [*move_command, "--confirm"])
    assert failed.exit_code != 0
    assert root.is_dir()
    assert not (destination / root.name).exists()
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["document_domain"] == "mywork/【Old】文档中心"

    monkeypatch.setattr(SqliteWorkspaceRepository, "save_projects", real_save_projects)
    moved = runner.invoke(app, [*move_command, "--confirm"])
    assert moved.exit_code == 0, moved.output
    moved_root = destination / root.name
    assert (moved_root / "_领域.md").is_file()
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["document_domain"] == "mywork/Destination/【Old】文档中心"


def test_domain_merge_moves_content_reparents_children_and_removes_source(
    workspace: Path,
) -> None:
    source = _create_domain(workspace, "Source", domain_id="source")
    target = _create_domain(workspace, "Target", domain_id="target")
    note = source / "记录-迁移.md"
    note.write_text(
        "---\nname: 迁移\ntype: record\ndomain: source\n---\n# 迁移\n",
        encoding="utf-8",
    )
    asset = source / "assets/diagram.bin"
    asset.parent.mkdir()
    asset.write_bytes(b"diagram")
    child = source / "Child"
    child.mkdir()
    (child / "_领域.md").write_text(
        "---\nname: Child\ndomain_id: child\ndomain_type: project-domain\n"
        "governance: project-docs\nmoc: '[[MOC-Child]]'\n"
        "parent_domain: source\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (child / "MOC-Child.md").write_text(
        "# MOC\n\n<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n",
        encoding="utf-8",
    )
    reference = workspace / "mywork/引用.canvas"
    reference.write_text("mywork/Source/记录-迁移.md\n", encoding="utf-8")
    command = [
        "workspace",
        "domain",
        "merge",
        "--source",
        "source",
        "--target",
        "target",
    ]

    preview = runner.invoke(app, command)
    preview_payload = json.loads(preview.output)
    assert preview.exit_code == 0, preview.output
    assert preview_payload["status"] == "planned"
    assert preview_payload["follow_up"] == []
    assert preview_payload["child_domain_count"] == 1
    assert preview_payload["reference_count"] == 1
    assert any(
        operation["action"] == "update-reference" and operation["path"] == "mywork/引用.canvas"
        for operation in preview_payload["operations"]
    )
    assert source.is_dir()

    applied = runner.invoke(app, [*command, "--confirm"])
    payload = json.loads(applied.output)
    assert applied.exit_code == 0, applied.output
    assert payload["status"] == "applied"
    assert payload["follow_up"] == [
        {"command": "maintenance sync", "workspace": "test", "scope": "mywork"}
    ]
    assert not source.exists()
    moved_note = target / "记录-迁移.md"
    assert parse_yaml_frontmatter(moved_note)["domain"] == "target"
    assert (target / "assets/diagram.bin").read_bytes() == b"diagram"
    assert parse_yaml_frontmatter(target / "Child/_领域.md")["parent_domain"] == "target"
    assert "mywork/Target/记录-迁移.md" in reference.read_text(encoding="utf-8")


def test_domain_merge_rebinds_project_root_atomically(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = workspace / "mywork/Source"
    target = workspace / "mywork/Target"
    write_domain_marker(source, "source", "Source", project_id="example")
    write_domain_marker(target, "target", "Target", project_id="example")
    note = source / "记录-迁移.md"
    note.write_text("# 迁移\n", encoding="utf-8")
    (workspace / ".campfire.yaml").write_text(
        "schema_version: 1\nworkspace:\n  id: test\n  name: Test\n"
        "  governance_version: 1\nprojects: []\n",
        encoding="utf-8",
    )
    adopted = runner.invoke(
        app,
        [
            "workspace",
            "project",
            "adopt",
            "--id",
            "example",
            "--name",
            "Example",
            "--domain",
            "source",
        ],
    )
    assert adopted.exit_code == 0, adopted.output

    command = [
        "workspace",
        "domain",
        "merge",
        "--source",
        "source",
        "--target",
        "target",
    ]
    preview = json.loads(runner.invoke(app, command).output)
    assert preview["affected_projects"] == ["example"]

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
    assert source.is_dir()
    assert not (target / note.name).exists()
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["document_domain"] == "mywork/Source"

    monkeypatch.setattr(SqliteWorkspaceRepository, "save_projects", real_save_projects)
    applied = runner.invoke(app, [*command, "--confirm"])
    assert applied.exit_code == 0, applied.output
    assert (target / note.name).is_file()
    project = json.loads(runner.invoke(app, ["workspace", "project", "show", "example"]).output)
    assert project["document_domain"] == "mywork/Target"
    manifest = yaml.safe_load((workspace / ".campfire.yaml").read_text(encoding="utf-8"))
    assert manifest["projects"][0]["document_domain"] == "mywork/Target"


def test_domain_merge_blocks_a_concurrent_source_change(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _create_domain(workspace, "Source", domain_id="source")
    target = _create_domain(workspace, "Target", domain_id="target")
    note = source / "记录-并发.md"
    note.write_text("before\n", encoding="utf-8")
    real_transaction = FileChangeExecutor.transaction

    @contextmanager
    def inject_change(executor, changes):
        note.write_text("concurrent\n", encoding="utf-8")
        with real_transaction(executor, changes):
            yield

    monkeypatch.setattr(FileChangeExecutor, "transaction", inject_change)
    result = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "merge",
            "--source",
            "source",
            "--target",
            "target",
            "--confirm",
        ],
    )

    assert result.exit_code == 3
    assert "发生变化" in result.output
    assert note.read_text(encoding="utf-8") == "concurrent\n"
    assert not (target / note.name).exists()


def test_domain_merge_blocks_conflicts_and_authored_declarations(workspace: Path) -> None:
    source = _create_domain(workspace, "Source", domain_id="source")
    target = _create_domain(workspace, "Target", domain_id="target")
    (source / "记录-冲突.md").write_text("source\n", encoding="utf-8")
    (target / "记录-冲突.md").write_text("target\n", encoding="utf-8")
    (source / "_领域.md").write_text(
        (source / "_领域.md").read_text(encoding="utf-8") + "\n人工边界说明。\n",
        encoding="utf-8",
    )
    (source / "MOC-Source.md").write_text(
        (source / "MOC-Source.md").read_text(encoding="utf-8") + "\n人工导航说明。\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "merge",
            "--source",
            "source",
            "--target",
            "target",
            "--confirm",
        ],
    )

    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert {issue["code"] for issue in payload["issues"]} >= {
        "domain-merge-target-exists",
        "domain-merge-authored-marker",
        "domain-merge-authored-moc",
    }
    assert source.is_dir()


def test_domain_merge_rejects_cycles_and_project_conflicts(workspace: Path) -> None:
    source = _create_domain(workspace, "Source", domain_id="source")
    child = source / "Child"
    write_domain_marker(child, "child", "Child")
    cycle = json.loads(
        runner.invoke(
            app,
            ["workspace", "domain", "merge", "--source", "source", "--target", "child"],
        ).output
    )
    assert cycle["status"] == "blocked"
    assert "domain-merge-target-inside-source" in {issue["code"] for issue in cycle["issues"]}

    left = workspace / "mywork/Left"
    right = workspace / "mywork/Right"
    write_domain_marker(left, "left", "Left", project_id="left-project")
    write_domain_marker(right, "right", "Right", project_id="right-project")
    conflict = json.loads(
        runner.invoke(
            app,
            ["workspace", "domain", "merge", "--source", "left", "--target", "right"],
        ).output
    )
    assert conflict["status"] == "blocked"
    assert "domain-merge-project-conflict" in {issue["code"] for issue in conflict["issues"]}


def test_domain_merge_can_cross_spaces_when_governance_matches(workspace: Path) -> None:
    source = workspace / "mywork/Source"
    target = workspace / "mynote/Target"
    write_domain_marker(source, "source", "Source", governance="knowledge-docs")
    write_domain_marker(target, "target", "Target", governance="knowledge-docs")
    (source / "知识-迁移.md").write_text("# 跨 Space\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "merge",
            "--source",
            "source",
            "--target",
            "target",
            "--confirm",
        ],
    )

    payload = json.loads(result.output)
    assert payload["status"] == "applied"
    assert (target / "知识-迁移.md").is_file()
    assert payload["follow_up"] == [
        {"command": "maintenance sync", "workspace": "test", "scope": "."}
    ]


def test_domain_merge_can_move_between_different_parents(workspace: Path) -> None:
    left = workspace / "mywork/Left"
    right = workspace / "mywork/Right"
    write_domain_marker(left, "left", "Left")
    write_domain_marker(right, "right", "Right")
    source = left / "Source"
    target = right / "Target"
    write_domain_marker(source, "source", "Source", parent_domain="left")
    write_domain_marker(target, "target", "Target", parent_domain="right")
    (source / "记录-迁移.md").write_text("# 跨父级\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "merge",
            "--source",
            "source",
            "--target",
            "target",
            "--confirm",
        ],
    )

    assert json.loads(result.output)["status"] == "applied"
    assert not source.exists()
    assert (target / "记录-迁移.md").is_file()


def test_domain_delete_only_removes_logically_empty_domain(workspace: Path) -> None:
    empty = _create_domain(workspace, "Empty", domain_id="empty")
    command = ["workspace", "domain", "delete", "--domain", "empty"]
    preview = runner.invoke(app, command)
    preview_payload = json.loads(preview.output)
    assert preview_payload["status"] == "planned"
    assert preview_payload["follow_up"] == []
    assert {operation["action"] for operation in preview_payload["operations"]} == {
        "delete-file",
        "delete-directory",
    }
    assert empty.is_dir()

    applied = runner.invoke(app, [*command, "--confirm"])
    payload = json.loads(applied.output)
    assert applied.exit_code == 0, applied.output
    assert payload["status"] == "applied"
    assert payload["follow_up"] == [
        {"command": "maintenance sync", "workspace": "test", "scope": "mywork"}
    ]
    assert not empty.exists()

    nonempty = _create_domain(workspace, "Nonempty", domain_id="nonempty")
    (nonempty / "记录-保留.md").write_text("keep\n", encoding="utf-8")
    blocked = runner.invoke(
        app,
        [
            "workspace",
            "domain",
            "delete",
            "--domain",
            "nonempty",
            "--confirm",
        ],
    )
    blocked_payload = json.loads(blocked.output)
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["issues"][0]["code"] == "domain-delete-not-empty"
    assert "domain merge" in blocked_payload["issues"][0]["hint"]
    assert nonempty.is_dir()


def test_domain_delete_blocks_authored_child_and_project_domains(workspace: Path) -> None:
    authored = _create_domain(workspace, "Authored", domain_id="authored")
    (authored / "MOC-Authored.md").write_text(
        (authored / "MOC-Authored.md").read_text(encoding="utf-8") + "\n人工说明。\n",
        encoding="utf-8",
    )
    authored_result = json.loads(
        runner.invoke(
            app,
            ["workspace", "domain", "delete", "--domain", "authored", "--confirm"],
        ).output
    )
    assert "domain-delete-authored-moc" in {issue["code"] for issue in authored_result["issues"]}

    parent = _create_domain(workspace, "Parent", domain_id="parent")
    write_domain_marker(parent / "Child", "child", "Child")
    child_result = json.loads(
        runner.invoke(
            app,
            ["workspace", "domain", "delete", "--domain", "parent", "--confirm"],
        ).output
    )
    assert "domain-delete-child-domains" in {issue["code"] for issue in child_result["issues"]}

    project_root = _create_domain(workspace, "Project", domain_id="project-root")
    (workspace / ".campfire.yaml").write_text(
        "schema_version: 1\nworkspace:\n  id: test\n  name: Test\n"
        "  governance_version: 1\nprojects: []\n",
        encoding="utf-8",
    )
    adopted = runner.invoke(
        app,
        [
            "workspace",
            "project",
            "adopt",
            "--id",
            "example",
            "--name",
            "Example",
            "--domain",
            "project-root",
        ],
    )
    assert adopted.exit_code == 0, adopted.output
    project_result = json.loads(
        runner.invoke(
            app,
            ["workspace", "domain", "delete", "--domain", "project-root", "--confirm"],
        ).output
    )
    assert "domain-delete-project-bound" in {issue["code"] for issue in project_result["issues"]}
    assert project_root.is_dir()


def test_domain_delete_follow_up_removes_last_index_projection(workspace: Path) -> None:
    import sqlite3

    domain = _create_domain(workspace, "Last", domain_id="last")
    runner.invoke(app, ["maintenance", "sync", "--scope", "mywork"])
    database = workspace / "_campfire/campfire.db"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "select domain_id from domains where workspace_id = 'test'"
        ).fetchall() == [("last",)]

    deleted = runner.invoke(
        app,
        ["workspace", "domain", "delete", "--domain", "last", "--confirm"],
    )
    assert json.loads(deleted.output)["status"] == "applied"
    assert not domain.exists()
    synced = runner.invoke(app, ["maintenance", "sync", "--scope", "mywork"])
    assert json.loads(synced.output)["status"] == "synced"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "select count(*) from domains where workspace_id = 'test'"
        ).fetchone() == (0,)


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
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-docs",
    ]
    preview = runner.invoke(app, command)
    assert preview.exit_code == 0, preview.output
    preview_payload = json.loads(preview.output)
    assert preview_payload["status"] == "planned"
    assert preview_payload["follow_up"] == []
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
        "--id",
        "knowledge-loose-notes",
        "--name",
        "零散笔记",
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

    first = runner.invoke(app, ["--workspace", "test", "maintenance", "sync"])
    assert first.exit_code == 0, first.output
    assert json.loads(first.output)["status"] == "synced", first.output

    relation_page = domain / "generated" / "相关文档-知识领域.md"
    assert relation_page.is_file()
    # 模拟旧版本在 Windows 上写出的 CRLF 生成文件
    relation_page.write_bytes(
        relation_page.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    second = runner.invoke(app, ["--workspace", "test", "maintenance", "sync"])
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
    applied = runner.invoke(app, ["--workspace", "test", "skill", "sync"])
    assert applied.exit_code == 0, applied.output

    target = next((workspace / "_global_skills").glob("campfire-document-capture/SKILL.md"))
    stale = target.read_text(encoding="utf-8") + "\n<!-- 旧版本残留 -->\n"
    target.write_bytes(stale.replace("\n", "\r\n").encode("utf-8"))

    result = runner.invoke(app, ["--workspace", "test", "skill", "sync"])
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
    runner.invoke(app, ["setup", "--path", str(workspace), "--id", "personal", "--default"])
    registered_app = monorepo / "apps" / "registered-app"
    registered_app.mkdir(parents=True)
    (workspace / "mywork").mkdir()
    (workspace / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    domain_dir = workspace / "mywork" / "example"
    write_domain_marker(
        domain_dir,
        "project-registered-app",
        "Registered App",
        project_id="registered-app",
    )
    added = runner.invoke(
        app,
        [
            "--workspace",
            "personal",
            "workspace",
            "project",
            "adopt",
            "--id",
            "registered-app",
            "--name",
            "Registered App",
            "--domain",
            "project-registered-app",
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
    first = runner.invoke(app, ["setup", "--path", str(workspace), "--id", "test"])
    assert first.exit_code == 0, first.output
    payload = json.loads(first.output)
    actions = payload["resources"]["agent_hints"]
    assert {item["action"] for item in actions} == {"created"}
    for item in [claude_md, agents_md]:
        assert "campfire:agent-hints:start" in item.read_text(encoding="utf-8")

    second = runner.invoke(app, ["setup", "--path", str(workspace)])
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
    assert "campfire setup --path <vault路径> [--id <id>] --default" in commands
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
