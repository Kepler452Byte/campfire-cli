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
        ["tree", "-h"],
        ["migration", "-h"],
        ["migration", "inventory", "-h"],
        ["maintenance", "-h"],
        ["maintenance", "check", "-h"],
        ["maintenance", "archive", "-h"],
        ["skill", "-h"],
        ["base", "-h"],
        ["workspace", "-h"],
        ["workspace", "project", "-h"],
        ["workspace", "project", "add", "-h"],
        ["workspace", "project", "create", "-h"],
        ["workspace", "project", "resolve", "-h"],
        ["workspace", "project", "check", "-h"],
        ["document", "-h"],
        ["document", "profile", "-h"],
        ["document", "profile", "show", "-h"],
        ["document", "type", "-h"],
        ["document", "type", "list", "-h"],
        ["document", "check", "-h"],
        ["document", "format", "-h"],
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


def test_project_is_not_exposed_as_a_top_level_command() -> None:
    result = runner.invoke(app, ["project", "-h"])
    assert result.exit_code != 0


def test_init_creates_defaults_without_overwriting_existing_file(
    tmp_path: Path, monkeypatch
) -> None:
    campfire_home = tmp_path / "campfire-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    existing = campfire_home / "workspaces" / "new-workspace" / "config" / "governance.json"
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
    assert schema["profiles"]["project-doc"]["enums"]["lifecycle"] == [
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
    repeated = runner.invoke(
        app,
        ["workspace", "create", "--id", "new", "--path", str(target)],
    )
    assert repeated.exit_code != 0


def test_project_registry_and_json_transfer(tmp_path: Path, monkeypatch) -> None:
    campfire_home = tmp_path / "campfire-home"
    workspace = tmp_path / "workspace"
    domain = workspace / "mywork" / "【Example】文档中心"
    repository = tmp_path / "repository"
    domain.mkdir(parents=True)
    repository.mkdir()
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    added_workspace = runner.invoke(
        app, ["workspace", "add", "--id", "personal", "--path", str(workspace), "--default"]
    )
    assert added_workspace.exit_code == 0, added_workspace.output
    added = runner.invoke(
        app,
        [
            "workspace",
            "project",
            "add",
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
    repository.mkdir()
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    added = runner.invoke(
        app,
        ["workspace", "add", "--id", "personal", "--path", str(workspace), "--default"],
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
    checked = runner.invoke(app, ["workspace", "project", "check", "new-project"])
    assert json.loads(checked.output)["status"] == "ok"


def test_unified_database_isolates_document_state_by_workspace(tmp_path: Path, monkeypatch) -> None:
    campfire_home = tmp_path / "campfire-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    for workspace_id in ("left", "right"):
        root = tmp_path / workspace_id
        root.mkdir()
        added = runner.invoke(
            app,
            ["workspace", "add", "--id", workspace_id, "--path", str(root)],
        )
        assert added.exit_code == 0, added.output
        note = root / "mynote" / "知识-相同路径.md"
        note.parent.mkdir()
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
    assert (workspace / "_global_skills/campfire-workspace-governance/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-context-bootstrap/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-conversation-router/SKILL.md").is_file()
    assert (workspace / "_global_skills/campfire-document-capture/SKILL.md").is_file()
    repeated = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync", "--dry-run"])
    assert json.loads(repeated.output)["operations"] == []
    checked = runner.invoke(app, ["--workspace", str(workspace), "skill", "check"])
    assert json.loads(checked.output)["status"] == "ok"


def test_skill_sync_deletes_only_explicitly_retired_packaged_skills(workspace: Path) -> None:
    target = workspace / "_global_skills"
    retired = target / "campfire-conversation-intake"
    custom = target / "custom-skill"
    retired.mkdir(parents=True)
    custom.mkdir(parents=True)
    (retired / "SKILL.md").write_text("retired", encoding="utf-8")
    (custom / "SKILL.md").write_text("custom", encoding="utf-8")

    preview = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync", "--dry-run"])
    operations = json.loads(preview.output)["operations"]
    assert any(
        item["action"] == "delete" and "conversation-intake" in item["path"] for item in operations
    )
    assert not any(
        item["action"] == "delete" and "custom-skill" in item["path"] for item in operations
    )

    applied = runner.invoke(app, ["--workspace", str(workspace), "skill", "sync"])
    assert applied.exit_code == 0, applied.output
    assert not retired.exists()
    assert (custom / "SKILL.md").is_file()


def test_skill_resolve_routes_inbox_and_knowledge(workspace: Path) -> None:
    for path, expected in (
        ("_收件箱/用户输入/test.md", "campfire-inbox-triage"),
        ("mynote/【知识】软件开发/test.md", "mynote-knowledge-governance"),
    ):
        result = runner.invoke(
            app, ["--workspace", str(workspace), "skill", "resolve", "--path", path]
        )
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


def test_document_profile_sync_requires_confirmation(workspace: Path) -> None:
    path = workspace / "_campfire/workspaces/test/config/frontmatter-schema.json"
    path.write_text(
        '{"version": 1, "profiles": {"custom": {"field_order": [], '
        '"required": [], "optional": []}}}\n',
        encoding="utf-8",
    )
    preview = runner.invoke(app, ["--workspace", str(workspace), "document", "profile", "sync"])
    assert json.loads(preview.output)["status"] == "planned"
    assert json.loads(path.read_text())["version"] == 1
    applied = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "document",
            "profile",
            "sync",
            "--confirm",
        ],
    )
    assert json.loads(applied.output)["status"] == "synced"
    assert json.loads(path.read_text())["version"] == 2
    assert "custom" in json.loads(path.read_text())["profiles"]


def test_document_type_sync_requires_confirmation(workspace: Path) -> None:
    path = workspace / "_campfire/workspaces/test/config/document-types.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    contract["types"].pop("board")
    contract["types"].pop("human-request")
    contract["profiles"]["project-docs"].remove("board")
    contract["types"]["custom"] = {"prefix": "自定义-", "label": "自定义"}
    path.write_text(json.dumps(contract), encoding="utf-8")

    preview = runner.invoke(app, ["--workspace", str(workspace), "document", "type", "sync"])
    assert json.loads(preview.output)["status"] == "planned"
    assert "board" not in json.loads(path.read_text())["types"]

    applied = runner.invoke(
        app,
        ["--workspace", str(workspace), "document", "type", "sync", "--confirm"],
    )
    assert json.loads(applied.output)["status"] == "synced"
    updated = json.loads(path.read_text())
    assert updated["types"]["board"]["prefix"] == "看板-"
    assert updated["types"]["human-request"]["prefix"] == "待确认-"
    assert "_收件箱/待用户确认" in updated["scope_roots"]
    assert "board" in updated["profiles"]["project-docs"]
    assert updated["types"]["custom"]["prefix"] == "自定义-"


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
    assert json.loads(checked.output)["status"] == "ok"

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
    config_path = workspace / "_campfire/workspaces/test/config"
    types = json.loads((config_path / "document-types.json").read_text())
    types["types"]["task"] = {"prefix": "任务-", "label": "任务"}
    (config_path / "document-types.json").write_text(json.dumps(types), encoding="utf-8")
    schema = json.loads((config_path / "frontmatter-schema.json").read_text())
    schema["profiles"]["task"]["enums"]["lifecycle"] = ["blocked", "completed"]
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
    missing = {
        issue["field"]
        for issue in payload["issues"]
        if issue["code"] == "frontmatter-field-missing"
    }
    assert {"requested_by", "blocked_reason"} <= missing


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
            [
                "--workspace",
                str(workspace),
                "migration",
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
            app, ["--workspace", str(workspace), "migration", "plan", "--batch", "b1"]
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
        [
            "--workspace",
            str(workspace),
            "migration",
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
            "migration",
            "plan",
            "--batch",
            "move",
            "--spec",
            str(spec),
        ],
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
        [
            "--workspace",
            str(workspace),
            "migration",
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
            "migration",
            "plan",
            "--batch",
            "links",
            "--spec",
            str(spec),
        ],
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
        [
            "--workspace",
            str(workspace),
            "migration",
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
            "migration",
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
    result = runner.invoke(
        app, ["--workspace", str(workspace), "maintenance", "apply", "--confirm"]
    )
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert payload["issues"][0]["code"] == "concurrent-change"


def test_maintenance_check_validates_skill_template_enums(workspace: Path) -> None:
    config = workspace / "_campfire/workspaces/test/config"
    types = json.loads((config / "document-types.json").read_text(encoding="utf-8"))
    types["types"]["task"] = {"prefix": "任务-", "label": "任务"}
    (config / "document-types.json").write_text(json.dumps(types), encoding="utf-8")
    schema = json.loads((config / "frontmatter-schema.json").read_text(encoding="utf-8"))
    schema["profiles"]["task"]["enums"]["lifecycle"] = ["todo", "completed"]
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


def _create_domain(workspace: Path, name: str, *, create_moc: bool = True) -> Path:
    domain = workspace / "mywork" / name
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"domain_id: {name.lower()}\n"
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
    config = workspace / "_campfire/workspaces/test/config/governance.json"
    governance = json.loads(config.read_text(encoding="utf-8"))
    governance["managed_roots"] = ["mywork/Project"]
    config.write_text(json.dumps(governance), encoding="utf-8")
    domain = _create_domain(workspace, "Project")
    (domain / "需求-旧文档.md").write_text("# 缺少元数据\n", encoding="utf-8")

    result = runner.invoke(app, ["--workspace", str(workspace), "maintenance", "run"])

    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["status"] == "needs-review"
    assert payload["write_performed"] is False
    assert "frontmatter-missing" in payload["issue_counts"]
    assert "需求-旧文档" in (domain / "MOC-Project.md").read_text(encoding="utf-8")


def test_scoped_sync_ignores_structural_issue_outside_scope(workspace: Path) -> None:
    config = workspace / "_campfire/workspaces/test/config/governance.json"
    governance = json.loads(config.read_text(encoding="utf-8"))
    governance["managed_roots"] = ["mywork/Healthy", "mywork/Broken"]
    config.write_text(json.dumps(governance), encoding="utf-8")
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
    assert payload["write_performed"] is True
    assert "记录-进展" in (healthy / "MOC-Healthy.md").read_text(encoding="utf-8")
