from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.main import app


def test_root_templates_use_existing_document_lifecycle(tmp_path: Path) -> None:
    runner = CliRunner()

    def invoke(*args: str) -> dict:
        result = runner.invoke(app, list(args))
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    root = tmp_path / "vault"
    invoke("workspace", "create", "--id", "demo", "--path", str(root), "--demo", "hello-world")
    assert (root / "_模板").is_dir()
    seeded = {"_模板/模板-任务.md", "_模板/模板-版本发布清单.md"}
    assert (root / "_模板/README.md").is_file()
    for target in seeded:
        assert (root / target).is_file()

    def command(*args: str) -> dict:
        return invoke("--workspace", "demo", *args)

    targets = []
    for directory in ("_模板", "mywork/【Hello World】文档中心/_模板"):
        args = (
            "document",
            "apply",
            "--path",
            f"{directory}/自定义任务",
            "--type",
            "template",
            "--set",
            "description=任务正文参考，可裁剪",
        )
        preview = command(*args)
        assert preview["status"] == "planned"
        assert not (root / preview["target"]).exists()
        applied = command(*args, "--expected-hash", preview["expected_hash"], "--confirm")
        assert applied["status"] == "applied"
        target = applied["target"]
        targets.append(target)
        path = root / target
        original = path.read_text(encoding="utf-8")
        body = "\n# 任务模板\n\n适用类型：task；按需裁剪。\n\n## 当前目标与范围\n"
        path.write_text(original + body, encoding="utf-8")
        assert parse_document(path.read_text(encoding="utf-8")).frontmatter == (
            parse_document(original).frontmatter
        )
        assert command("document", "check", "--path", target)["status"] == "ok"
        assert command("document", "inspect", "--path", target)["profile"]["name"] == "base"
        for follow_up in applied["follow_up"]:
            assert (
                command("maintenance", "sync", "--scope", follow_up["scope"])["status"] == "synced"
            )
        assert command("maintenance", "check", "--scope", directory)["issue_count"] == 0
        assert path.read_text(encoding="utf-8").endswith(body)

    listed = command("document", "list", "--type", "template")
    assert {item["path"] for item in listed["items"]} == set(targets) | seeded
    # A template is a content reference, not a new Domain or a required task layout.
    assert not (root / "_模板/_领域.md").exists()
    args = (
        "document",
        "apply",
        "--path",
        "mywork/【Hello World】文档中心/简单待办",
        "--type",
        "task",
        "--set",
        "description=确认安装",
        "--set",
        "task_status=todo",
    )
    planned = command(*args)
    result = command(*args, "--expected-hash", planned["expected_hash"], "--confirm")
    path = root / result["target"]
    path.write_text(path.read_text(encoding="utf-8") + "\n确认安装可用即可。\n", encoding="utf-8")
    assert command("document", "check", "--path", result["target"])["status"] == "ok"

    # A new session reads the current goal; renaming and state updates preserve that handoff.
    current = path.read_text(encoding="utf-8")
    handoff = (
        "\n## 当前目标与范围\n用户确认改为验证离线安装。\n"
        "\n## 当前进展与交接\n已验证在线安装；缺离线包，下一步获取包。\n"
        "\n## 工作清单\n取消：在线重装测试，已退出范围。\n"
        "\n## 关键变更记录\n用户确认缩小验收范围，保留已有结果。\n"
    )
    path.write_text(current + handoff, encoding="utf-8")
    rename = ("document", "rename", "--path", result["target"], "--name", "验证离线安装")
    preview = command(*rename)
    renamed = command(
        *rename,
        "--expected-hash",
        preview["expected_hash"],
        "--expected-plan",
        preview["expected_plan"],
        "--confirm",
    )
    assert not path.exists()
    new_path = root / renamed["target"]
    assert new_path.read_text(encoding="utf-8").endswith(handoff)
    update = ("document", "apply", "--path", renamed["target"], "--set", "task_status=blocked")
    preview = command(*update)
    command(*update, "--expected-hash", preview["expected_hash"], "--confirm")
    parsed = parse_document(new_path.read_text(encoding="utf-8"))
    assert parsed.frontmatter["task_status"] == "blocked"
    assert new_path.read_text(encoding="utf-8").endswith(handoff)
    assert command("document", "check", "--path", renamed["target"])["status"] == "ok"


def test_template_directory_contract_still_blocks_wrong_types(workspace: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--workspace",
            "test",
            "document",
            "apply",
            "--path",
            "_模板/普通记录",
            "--type",
            "record",
            "--set",
            "description=不应写入",
            "--confirm",
        ],
    )
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert any(issue["code"] == "template-directory-type-mismatch" for issue in payload["issues"])
    assert not list((workspace / "_模板").glob("*.md"))


@pytest.mark.parametrize("demo", [False, True])
def test_starter_templates_are_created_once_and_not_synced(tmp_path, monkeypatch, demo) -> None:
    runner = CliRunner()

    def invoke(*args):
        result = runner.invoke(app, list(args))
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    root = tmp_path / "new"
    args = ["workspace", "create", "--id", "new", "--path", str(root)]
    if demo:
        args.extend(["--demo", "hello-world"])
    created = invoke(*args)
    expected = {"README.md", "模板-任务.md", "模板-版本发布清单.md"}
    assert {path.name for path in (root / "_模板").iterdir()} == expected
    assert {str(root / "_模板" / name) for name in expected} <= set(created["created"])
    listed = invoke("--workspace", "new", "document", "list", "--type", "template")
    assert listed["count"] == 2
    for item in listed["items"]:
        path = root / item["path"]
        data = parse_document(path.read_text(encoding="utf-8")).frontmatter
        assert str(data["created"]) == date.today().isoformat()
        assert str(data["updated"]) == date.today().isoformat()
        assert data["type"] == "template"
        assert (
            invoke("--workspace", "new", "document", "check", "--path", item["path"])["status"]
            == "ok"
        )
    assert invoke("--workspace", "new", "document", "list", "--type", "task")["count"] == 0

    task = root / "_模板/模板-任务.md"
    modified = task.read_text(encoding="utf-8") + "\n用户自己的规范。\n"
    task.write_text(modified, encoding="utf-8")
    (root / "_模板/模板-版本发布清单.md").unlink()
    invoke("setup", "--path", str(root))
    monkeypatch.setattr("campfire_cli.container.fetch_latest_version", lambda _: None)
    invoke("upgrade", "--skip-package")
    assert task.read_text(encoding="utf-8") == modified
    assert not (root / "_模板/模板-版本发布清单.md").exists()

    existing = tmp_path / "existing"
    existing.mkdir()
    invoke("setup", "--path", str(existing), "--id", "existing")
    assert not (existing / "_模板").exists()
