from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from campfire_cli.main import app

runner = CliRunner()


def test_short_help_is_available_at_every_command_level() -> None:
    commands = [
        ["-h"],
        ["migration", "-h"],
        ["migration", "inventory", "-h"],
        ["maintenance", "-h"],
        ["maintenance", "check", "-h"],
        ["archive", "-h"],
        ["database", "-h"],
        ["skill", "-h"],
        ["base", "-h"],
        ["workspace", "-h"],
    ]
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, (command, result.output)
        assert "help" in result.output.lower()


def test_init_creates_defaults_without_overwriting_existing_file(
    tmp_path: Path, monkeypatch
) -> None:
    vg_home = tmp_path / "campfire-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(vg_home))
    existing = vg_home / "workspaces" / "new-workspace" / "config" / "governance.json"
    existing.parent.mkdir(parents=True)
    existing.write_text('{"custom": true}\n', encoding="utf-8")
    result = runner.invoke(
        app, ["init", "--id", "new-workspace", "--workspace", str(tmp_path), "--default"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "initialized"
    assert json.loads(existing.read_text(encoding="utf-8")) == {"custom": True}
    assert (existing.parent / "document-types.json").is_file()
    assert (existing.parent / "frontmatter-schema.json").is_file()
    assert (existing.parent / "skills.json").is_file()
    assert (existing.parent / "bases.json").is_file()
    schema = json.loads((existing.parent / "frontmatter-schema.json").read_text(encoding="utf-8"))
    assert schema["profiles"]["project-docs"]["enums"]["lifecycle"] == [
        "maintained",
        "proposed",
        "completed",
        "archived",
    ]
    assert not (tmp_path / ".campfire").exists()
    resolved = runner.invoke(app, ["workspace", "resolve", "--workspace", "new-workspace"])
    assert json.loads(resolved.output)["workspace"] == str(tmp_path)


def test_multiple_registered_workspaces_can_be_selected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "campfire-home"))
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    runner.invoke(app, ["workspace", "add", "--id", "left", "--path", str(left), "--default"])
    runner.invoke(app, ["workspace", "add", "--id", "right", "--path", str(right)])
    listed = json.loads(runner.invoke(app, ["workspace", "list"]).output)
    assert listed["default_workspace"] == "left"
    assert set(listed["workspaces"]) == {"left", "right"}
    shown = json.loads(runner.invoke(app, ["workspace", "show", "right"]).output)
    assert shown["workspace"] == str(right)
    runner.invoke(app, ["workspace", "set-default", "right"])
    resolved = json.loads(runner.invoke(app, ["workspace", "resolve"]).output)
    assert resolved["workspace_id"] == "right"


def test_workspace_create_builds_minimal_scaffold_and_database(tmp_path: Path, monkeypatch) -> None:
    vg_home = tmp_path / "campfire-home"
    target = tmp_path / "new-workspace"
    monkeypatch.setenv("CAMPFIRE_HOME", str(vg_home))
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
    assert (vg_home / "workspaces/new/db/campfire.db").is_file()
    repeated = runner.invoke(
        app,
        ["workspace", "create", "--id", "new", "--path", str(target)],
    )
    assert repeated.exit_code != 0


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
    assert (workspace / "_global_skills/campfire-workspace-governance/SKILL.md").is_file()
    repeated = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync", "--dry-run"])
    assert json.loads(repeated.output)["operations"] == []
    checked = runner.invoke(app, ["--workspace", str(workspace), "skill", "check"])
    assert json.loads(checked.output)["status"] == "ok"


def test_skill_resolve_routes_inbox_and_knowledge(workspace: Path) -> None:
    for path, expected in (
        ("_收件箱/用户输入/test.md", "campfire-inbox-triage"),
        ("mynote/【知识】软件开发/test.md", "mynote-knowledge-governance"),
    ):
        result = runner.invoke(app, ["--workspace", str(workspace), "skill", "resolve", "--path", path])
        assert result.exit_code == 0, result.output
        names = [item["name"] for item in json.loads(result.output)["skills"]]
        assert "campfire-workspace-governance" in names
        assert expected in names


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
        "campfire-workspace-governance",
        "mywork-project-docs-governance",
        "mywork-task-governance",
    ]


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
    state = workspace / "_vg/workspaces/test"
    assert (state / "db/campfire.db").is_file()
    assert (state / "reports/current.json").is_file()
    assert (state / "reports/current.md").is_file()


def test_maintenance_check_validates_task_business_rules(workspace: Path) -> None:
    config_path = workspace / "_vg/workspaces/test/config"
    types = json.loads((config_path / "document-types.json").read_text())
    types["types"]["task"] = {"prefix": "任务-", "label": "任务"}
    (config_path / "document-types.json").write_text(json.dumps(types), encoding="utf-8")
    schema = json.loads((config_path / "frontmatter-schema.json").read_text())
    schema["profiles"]["task"] = {
        "types": ["task"],
        "required": ["task_id", "task_source", "source_channel", "assignee", "requires_human"],
        "enums": {
            "lifecycle": ["blocked", "completed"],
            "task_source": ["personal", "assigned"],
            "source_channel": ["self", "im"],
        },
        "lists": ["assignee", "verification"],
    }
    (config_path / "frontmatter-schema.json").write_text(json.dumps(schema), encoding="utf-8")
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
    codes = {issue["code"] for issue in payload["issues"]}
    assert "task-requested-by-missing" in codes
    assert "task-blocked-reason-missing" in codes


def test_migration_plan_is_unapproved_and_hash_change_blocks_apply(workspace: Path) -> None:
    note = workspace / "mynote" / "知识-【Test】标题.md"
    note.write_text(
        "---\nname: 标题\ndescription: test\ntype: knowledge\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# 标题\n",
        encoding="utf-8",
    )
    assert (
        runner.invoke(
            app,
            ["--workspace", str(workspace), "migration", "inventory", "--scope", "mynote", "--batch", "b1"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["--workspace", str(workspace), "migration", "plan", "--batch", "b1"]).exit_code
        == 0
    )
    plan_path = workspace / "_vg/workspaces/test/batches/b1/plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["items"] and plan["items"][0]["approved"] is False
    plan["items"][0]["approved"] = True
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    note.write_text(note.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["--workspace", str(workspace), "migration", "apply", "--batch", "b1", "--confirm"],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "blocked"
    assert "source-hash-changed" in result.output


def test_migration_plan_spec_supports_cross_directory_move_and_metadata(workspace: Path) -> None:
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
        ["--workspace", str(workspace), "migration", "inventory", "--scope", "mynote", "--batch", "move"],
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
        ["--workspace", str(workspace), "migration", "plan", "--batch", "move", "--spec", str(spec)],
    )
    assert json.loads(planned.output)["item_count"] == 1
    applied = runner.invoke(
        app,
        ["--workspace", str(workspace), "migration", "apply", "--batch", "move", "--confirm"],
    )
    assert json.loads(applied.output)["status"] == "applied"
    target = workspace / "mywork" / "知识-迁移.md"
    assert target.is_file() and not source.exists()
    assert "status: draft" in target.read_text(encoding="utf-8")
    assert "mywork/知识-迁移.md" in reference.read_text(encoding="utf-8")


def test_migration_rewrites_unique_wikilink_without_replacing_plain_text(workspace: Path) -> None:
    source = workspace / "mynote/知识-旧标题.md"
    source.write_text("---\ntype: knowledge\n---\n", encoding="utf-8")
    reference = workspace / "mywork/知识-引用.md"
    reference.write_text("[[知识-旧标题]]\n正文知识-旧标题不应被替换\n", encoding="utf-8")
    runner.invoke(
        app,
        ["--workspace", str(workspace), "migration", "inventory", "--scope", "mynote", "--batch", "links"],
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
        app, ["--workspace", str(workspace), "migration", "plan", "--batch", "links", "--spec", str(spec)]
    )
    result = runner.invoke(
        app, ["--workspace", str(workspace), "migration", "apply", "--batch", "links", "--confirm"]
    )
    assert json.loads(result.output)["status"] == "applied"
    updated = reference.read_text(encoding="utf-8")
    assert "[[知识-新标题]]" in updated
    assert "正文知识-旧标题不应被替换" in updated


def test_migration_spec_rejects_invalid_enum_during_plan(workspace: Path) -> None:
    source = workspace / "mynote/知识-非法状态.md"
    source.write_text("---\ntype: knowledge\nstatus: current\n---\n", encoding="utf-8")
    runner.invoke(
        app,
        ["--workspace", str(workspace), "migration", "inventory", "--scope", "mynote", "--batch", "enum"],
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
        app, ["--workspace", str(workspace), "migration", "plan", "--batch", "enum", "--spec", str(spec)]
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


def test_filtered_check_preserves_overall_status(workspace: Path) -> None:
    (workspace / "mynote/坏文档.md").write_text("无 frontmatter\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["--workspace", str(workspace), "maintenance", "check", "--code", "template-enum-invalid"],
    )
    payload = json.loads(result.output)
    assert payload["issue_count"] == 0
    assert payload["total_issue_count"] > 0
    assert payload["status"] == "needs-review"


def test_maintenance_apply_blocks_when_snapshot_changed(workspace: Path) -> None:
    note = workspace / "mynote" / "知识-并发.md"
    note.write_text("# 并发\n", encoding="utf-8")
    runner.invoke(app, ["--workspace", str(workspace), "maintenance", "plan"])
    note.write_text("# 另一个会话修改\n", encoding="utf-8")
    result = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "apply", "--confirm"])
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert payload["issues"][0]["code"] == "concurrent-change"


def test_maintenance_check_validates_skill_template_enums(workspace: Path) -> None:
    config = workspace / "_vg/workspaces/test/config"
    types = json.loads((config / "document-types.json").read_text(encoding="utf-8"))
    types["types"]["task"] = {"prefix": "任务-", "label": "任务"}
    (config / "document-types.json").write_text(json.dumps(types), encoding="utf-8")
    schema = json.loads((config / "frontmatter-schema.json").read_text(encoding="utf-8"))
    schema["profiles"]["task"] = {
        "types": ["task"],
        "enums": {"lifecycle": ["todo", "completed"]},
    }
    (config / "frontmatter-schema.json").write_text(json.dumps(schema), encoding="utf-8")
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
