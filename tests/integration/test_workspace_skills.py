import json
import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry
from campfire_cli.config.settings import campfire_home
from campfire_cli.main import app


def cli(*args: str, exit_code: int = 0) -> dict:
    result = CliRunner().invoke(app, ["--workspace", "test", *args])
    assert result.exit_code == exit_code, result.output
    return json.loads(result.stdout if exit_code == 0 else result.stderr)


def configure(workspace: Path, roots: list[str]) -> None:
    manifest = workspace / ".campfire.yaml"
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["skills"] = {"roots": roots}
    manifest.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def test_workspace_skill_catalog_is_read_only_and_isolates_bad_entries(workspace: Path) -> None:
    assert cli("skill", "list", "--source", "workspace")["skills"] == []
    configure(
        workspace, ["work-skills", "mywork/团队", "work-skills/采购", "missing", "../outside"]
    )
    entries = []
    for root in ("work-skills/采购", "mywork/团队"):
        entry = workspace / root / "采购指南/SKILL.md"
        entry.parent.mkdir(parents=True)
        entry.write_text(
            "---\nname: 采购指南\ndescription: >-\n  整理采购规格\n  和候选商品\n"
            "metadata:\n  author: test\n---\n完整正文\n",
            encoding="utf-8",
        )
        entries.append(entry)
    broken = workspace / "work-skills/损坏/SKILL.md"
    broken.parent.mkdir()
    broken.write_text("---\nname: [\n---\n", encoding="utf-8")
    nested = broken.parent / "references/隐藏/SKILL.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("---\nname: 隐藏\ndescription: 不是独立技能\n---\n", encoding="utf-8")
    result = cli("skill", "list", "--source", "workspace")
    assert result["status"] == "needs-review"
    assert result["skills"] == [
        {"name": "采购指南", "description": "整理采购规格 和候选商品", "path": str(entry)}
        for entry in sorted(entries)
    ]
    assert {(item["code"], item["path"]) for item in result["issues"]} == {
        ("skill-root-invalid", "missing"),
        ("skill-root-invalid", "../outside"),
        ("skill-entry-invalid", str(broken)),
    }
    assert not (campfire_home() / "campfire.db").exists()
    assert "完整正文" in Path(result["skills"][0]["path"]).read_text(encoding="utf-8")
    assert "campfire-document-capture" in {
        skill["name"] for skill in cli("skill", "list")["skills"]
    }


def test_document_governance_excludes_the_whole_package(workspace: Path) -> None:
    cli(
        "workspace",
        "domain",
        "create",
        "--id",
        "demo",
        "--name",
        "Demo",
        "--path",
        "mynote/Demo",
        "--type",
        "knowledge-domain",
        "--confirm",
    )
    note = cli(
        "document",
        "apply",
        "--path",
        "mynote/Demo/说明",
        "--type",
        "knowledge",
        "--set",
        "description=普通文档",
        "--expected-hash",
        "missing",
        "--confirm",
    )["target"]
    roots = ["mynote/Demo"]
    configure(workspace, roots)
    FilesystemWorkspaceRepository(campfire_home()).replace_projects(
        "test",
        [
            ProjectEntry(
                id="example", name="Example", document_domain_id="demo", workspace_id="test"
            )
        ],
    )
    assert yaml.safe_load((workspace / ".campfire.yaml").read_text(encoding="utf-8"))["skills"] == {
        "roots": roots
    }
    package = workspace / "mynote/Demo/采购"
    resource = package / "references/规格.md"
    resource.parent.mkdir(parents=True)
    entry = package / "SKILL.md"
    entry.write_text("损坏入口也确定包边界\n", encoding="utf-8")
    resource.write_text("参考资料\n", encoding="utf-8")
    (resource.parent / "_领域.md").write_text("包内资源同名文件\n", encoding="utf-8")
    documents = cli("document", "list")["items"]
    assert note in {item["path"] for item in documents}
    assert not any("采购/" in item["path"] for item in documents)
    report = cli("maintenance", "check")
    assert not any("采购/" in str(item["path"]) for item in report["issues"])
    for path in (entry, resource):
        relative = path.relative_to(workspace).as_posix()
        assert cli("document", "format", "--path", relative, "--confirm")["status"] == (
            "not-applicable"
        )
        assert cli("document", "apply", "--path", relative, exit_code=3)["code"] == (
            "skill-package-unmanaged"
        )
        assert cli("document", "profile", "resolve", "--path", relative, exit_code=3)["code"] == (
            "skill-package-unmanaged"
        )
        assert (
            cli("document", "rename", "--path", relative, "--name", "改名", exit_code=3)["code"]
            == "skill-package-unmanaged"
        )
    assert resource.read_text(encoding="utf-8") == "参考资料\n"


def test_offline_resource_alignment_updates_the_agent_hint() -> None:
    hint = Path(os.environ["CAMPFIRE_AGENT_HINT_PATH"])
    hint.write_text("# 客户端原有说明\n", encoding="utf-8")
    cli("upgrade", "--skip-package")
    text = hint.read_text(encoding="utf-8")
    assert text.startswith("# 客户端原有说明\n")
    assert "campfire --workspace <id> skill list --source workspace" in text


@pytest.mark.parametrize("operation", ["rename", "merge", "move"])
def test_domain_relocation_reports_skill_root_repair(workspace: Path, operation: str) -> None:
    for domain in ("source", "target"):
        cli(
            "workspace",
            "domain",
            "create",
            "--id",
            domain,
            "--name",
            domain,
            "--path",
            f"mywork/{domain}",
            "--type",
            "work-domain",
            "--confirm",
        )
    targets = {
        "rename": ("mywork/renamed", ("--domain", "source", "--folder-name", "renamed")),
        "merge": ("mywork/target", ("--source", "source", "--target", "target")),
        "move": ("mywork/target/source", ("--domain", "source", "--target", "target")),
    }
    target, options = targets[operation]
    old_root = "mywork/source/skills"
    new_root = f"{target}/skills"
    configure(workspace, [old_root, "mynote"])
    manifest = workspace / ".campfire.yaml"
    original = manifest.read_bytes()
    entry = workspace / old_root / "demo/SKILL.md"
    entry.parent.mkdir(parents=True)
    entry.write_text("---\nname: demo\ndescription: Example skill\n---\n", encoding="utf-8")
    args = ("workspace", "domain", operation, *options)
    preview = cli(*args)
    assert not preview["write_performed"]
    assert [(issue["old_path"], issue["suggested_path"]) for issue in preview["issues"]] == [
        (old_root, new_root)
    ]
    confirmation = ("--expected-plan", preview["expected_plan"]) if operation == "rename" else ()
    applied = cli(*args, *confirmation, "--confirm")
    assert applied["status"] == "needs-review" and applied["write_performed"]
    assert [
        issue for issue in applied["issues"] if issue["code"] == "skill-root-path-changed"
    ] == preview["issues"]
    assert manifest.read_bytes() == original
    assert (workspace / new_root / "demo/SKILL.md").is_file()
    configure(workspace, [new_root, "mynote"])
    assert [item["name"] for item in cli("skill", "list", "--source", "workspace")["skills"]] == [
        "demo"
    ]
