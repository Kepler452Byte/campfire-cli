from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from campfire_cli.main import app

runner = CliRunner()


def test_apply_reports_independent_errors_without_writing(workspace: Path) -> None:
    domain = workspace / "mynote" / "Example"
    domain.mkdir()
    (domain / "_领域.md").write_text("---\ndomain_id: example\n---\n", encoding="utf-8")
    arguments = [
        "--workspace",
        "test",
        "document",
        "apply",
        "--path",
        "mynote/Example/任务",
        "--type",
        "task",
        "--set",
        "title=错误字段",
        "--set",
        "tags=not-json",
        "--confirm",
    ]
    result = runner.invoke(app, arguments)
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert set(payload["missing_fields"]) == {"description", "task_status"}
    issues = {(item["code"], item.get("field")): item for item in payload["issues"]}
    unknown = issues[("frontmatter-field-not-allowed", "title")]
    assert "name" in unknown["allowed"]
    assert ("frontmatter-list-invalid", "tags") in issues
    assert ("frontmatter-field-missing", "description") in issues
    assert ("frontmatter-field-missing", "task_status") in issues
    assert payload["follow_up"] == []
    assert payload["write_performed"] is False
    assert not (workspace / payload["target"]).exists()


def test_apply_path_base_and_domain_discovery_are_workspace_scoped(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = workspace / "mynote" / "Example"
    domain.mkdir()
    (domain / "_领域.md").write_text("---\ndomain_id: example\n---\n", encoding="utf-8")
    arguments = [
        "--workspace",
        "test",
        "document",
        "apply",
        "--path",
        "mynote/Example/note",
        "--type",
        "knowledge",
        "--set",
        "description=知识",
    ]
    at_root = json.loads(runner.invoke(app, arguments).output)
    monkeypatch.chdir(domain)
    at_child = json.loads(runner.invoke(app, arguments).output)
    assert at_root == at_child
    assert at_child["status"] == "planned"
    absolute = list(arguments)
    absolute[5] = str(domain / "note")
    assert json.loads(runner.invoke(app, absolute).output)["target"] == at_child["target"]

    arguments[5] = "note"
    rejected = runner.invoke(app, arguments)
    assert rejected.exit_code != 0
    error = json.loads(rejected.output)
    assert error["code"] == "domain-missing"
    assert error["path_base"] == "workspace"
    assert Path(error["resolved_path"]) == workspace / "知识-note.md"
    assert error["next_action"] == {
        "command": "workspace domain list",
        "arguments": {"workspace": "test"},
    }
    discovery = runner.invoke(app, ["--workspace", "test", "workspace", "domain", "list"])
    assert discovery.exit_code == 0, discovery.output


def test_public_tree_exposes_only_current_document_workflow() -> None:
    result = runner.invoke(app, ["tree"])
    assert result.exit_code == 0, result.output
    assert "document" in result.output
    assert "maintenance" in result.output
    assert "archive" not in result.output
    assert "decision" not in result.output


def test_document_apply_requires_path_option() -> None:
    result = runner.invoke(app, ["document", "apply", "--type", "task"])
    assert result.exit_code != 0
    command = get_command(app).commands["document"].commands["apply"]
    path = next(parameter for parameter in command.params if parameter.name == "path")
    assert path.required


def test_removed_lifecycle_filter_is_not_public() -> None:
    result = runner.invoke(app, ["document", "list", "--lifecycle", "proposed"])
    assert result.exit_code != 0


def test_document_apply_does_not_expose_body_editing_options() -> None:
    result = runner.invoke(app, ["document", "apply", "--help"])
    assert result.exit_code == 0, result.output
    assert "--body-file" not in result.output
    assert "--append-section" not in result.output
    assert "--replace-body" not in result.output


def test_document_rename_exposes_title_not_target_domain() -> None:
    command = get_command(app).commands["document"].commands["rename"]
    parameter_names = {parameter.name for parameter in command.params}
    assert {"source", "name"} <= parameter_names
    assert "target_domain" not in parameter_names


def test_cli_errors_use_one_json_envelope() -> None:
    cases = [
        (
            ["document", "apply", "--path", "note.md", "--set", "invalid"],
            "invalid-set",
        ),
        (["document", "apply", "--path", "note.md", "--bogus"], "invalid-option"),
        (["document", "apply", "--type", "task"], "missing-argument"),
        (["--workspace", "missing", "document", "profile", "show", "task"], "configuration-error"),
    ]
    for arguments, code in cases:
        result = runner.invoke(app, arguments)
        assert result.exit_code != 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "error"
        assert payload["code"] == code
        assert isinstance(payload["message"], str)


def test_document_type_list_is_structured(workspace: Path) -> None:
    result = runner.invoke(app, ["--workspace", "test", "document", "type", "list"])
    assert result.exit_code == 0, result.output
    names = {item["name"] for item in json.loads(result.output)["types"]}
    assert {"prd", "trd", "human-request", "task"} <= names
    assert not {"issue", "product-spec", "tech-spec", "requirement-doc"} & names


def test_first_time_workspace_create_and_existing_directory_setup(tmp_path: Path) -> None:
    created = tmp_path / "created"
    create = runner.invoke(
        app,
        ["workspace", "create", "--id", "created", "--path", str(created), "--default"],
    )
    assert create.exit_code == 0, create.output
    create_payload = json.loads(create.output)
    assert create_payload["resources"]["bases"]["status"] == "synced"
    assert create_payload["resources"]["skills"]["status"] == "synced"
    assert (created / ".campfire.yaml").is_file()
    assert (created / "治理视图" / "文档工作台.base").is_file()
    assert {
        "mynote",
        "mywork",
        "mylog",
        "myresearch",
        "myblog",
    } <= {path.name for path in created.iterdir() if path.is_dir()}

    planned_space = runner.invoke(
        app,
        [
            "--workspace",
            "created",
            "workspace",
            "space",
            "create",
            "--id",
            "custom",
            "--name",
            "自定义",
            "--path",
            "mycustom",
            "--type",
            "custom",
        ],
    )
    assert planned_space.exit_code == 0, planned_space.output
    assert json.loads(planned_space.output)["status"] == "planned"
    assert not (created / "mycustom").exists()

    created_space = runner.invoke(
        app,
        [
            "--workspace",
            "created",
            "workspace",
            "space",
            "create",
            "--id",
            "custom",
            "--name",
            "自定义",
            "--path",
            "mycustom",
            "--type",
            "custom",
            "--confirm",
        ],
    )
    assert created_space.exit_code == 0, created_space.output
    assert json.loads(created_space.output)["status"] == "created"
    assert (created / "mycustom" / "_空间.md").is_file()

    demo_workspace = tmp_path / "demo"
    demo = runner.invoke(
        app,
        [
            "workspace",
            "create",
            "--id",
            "demo",
            "--path",
            str(demo_workspace),
            "--demo",
            "hello-world",
        ],
    )
    assert demo.exit_code == 0, demo.output
    demo_payload = json.loads(demo.output)
    assert demo_payload["demo"]["project"]["git_remote_url"] == (
        "https://github.com/octocat/Hello-World.git"
    )
    assert "hello-world" in (demo_workspace / ".campfire.yaml").read_text(encoding="utf-8")

    project = runner.invoke(
        app, ["--workspace", "demo", "workspace", "project", "show", "hello-world"]
    )
    assert project.exit_code == 0, project.output
    assert json.loads(project.output)["document_domain_id"] == "project-hello-world"

    domain_check = runner.invoke(app, ["--workspace", "demo", "workspace", "domain", "check"])
    assert domain_check.exit_code == 0, domain_check.output
    assert json.loads(domain_check.output)["status"] == "ok"

    maintenance = runner.invoke(app, ["--workspace", "demo", "maintenance", "check", "--summary"])
    assert maintenance.exit_code == 0, maintenance.output
    assert json.loads(maintenance.output)["status"] == "ok"

    existing = tmp_path / "existing"
    existing.mkdir()
    setup = runner.invoke(app, ["setup", "--path", str(existing), "--id", "existing", "--default"])
    assert setup.exit_code == 0, setup.output
    assert json.loads(setup.output)["manifest_operation"] == "created"

    repeated = runner.invoke(app, ["setup", "--path", str(existing), "--default"])
    assert repeated.exit_code == 0, repeated.output
    assert json.loads(repeated.output)["manifest_operation"] == "preserved"

    skills = runner.invoke(app, ["--workspace", "existing", "skill", "list"])
    assert skills.exit_code == 0, skills.output
    names = {item["name"] for item in json.loads(skills.output)["skills"]}
    assert "campfire-workspace-onboarding" in names

    shown = runner.invoke(
        app, ["--workspace", "existing", "skill", "show", "campfire-workspace-onboarding"]
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["skills"][0]["status"] == "current"


def test_setup_rejects_an_invalid_existing_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "invalid"
    workspace.mkdir()
    (workspace / ".campfire.yaml").write_text("workspace: invalid\n", encoding="utf-8")

    result = runner.invoke(app, ["setup", "--path", str(workspace)])

    assert result.exit_code != 0
    assert (workspace / ".campfire.yaml").read_text(encoding="utf-8") == "workspace: invalid\n"


def test_relationships_follow_rename_move_and_retype(workspace: Path) -> None:
    for name in ("First", "Second"):
        domain = workspace / "mynote" / name
        domain.mkdir()
        (domain / "_领域.md").write_text(
            f"---\nname: {name}\ndomain_id: {name.lower()}\ndomain_type: knowledge-domain\n"
            f"governance: knowledge-docs\nmoc: MOC-{name}\nstatus: active\n---\n",
            encoding="utf-8",
        )

    def call(*args):
        result = runner.invoke(app, ["--workspace", "test", "document", *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    target = call(
        "apply",
        "--path",
        "mynote/First/目标",
        "--type",
        "record",
        "--set",
        "description=目标",
        "--confirm",
    )["target"]
    source = call(
        "apply",
        "--path",
        "mynote/First/引用",
        "--type",
        "record",
        "--set",
        "description=引用",
        "--set",
        f'related_docs=["[[{target}]]"]',
        "--confirm",
    )["target"]
    for command in (
        ["rename", "--name", "新标题"],
        ["move", "--domain", "second"],
        ["apply", "--type", "plan"],
    ):
        args = [*command, "--path", target]
        preview = call(*args)
        result = call(
            *args,
            "--expected-hash",
            preview["expected_hash"],
            "--expected-plan",
            preview["expected_plan"],
            "--confirm",
        )
        assert result["write_performed"]
        target = result["target"]
        assert call("inspect", "--path", source)["relations"]["outgoing"][0]["target"] == target
        assert call("inspect", "--path", target)["relations"]["incoming"][0]["source"] == source
    cleared = call("apply", "--path", source, "--set", "related_docs=[]", "--confirm")
    assert cleared["write_performed"]
    assert call("inspect", "--path", target)["relations"]["in_degree"] == 0
