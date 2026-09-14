from __future__ import annotations

from pathlib import Path

from campfire_cli.app.document.service.document_service import DocumentService
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.config.settings import WorkspaceSettings


def service(workspace: Path) -> DocumentService:
    return DocumentService(WorkspaceSettings.load("test", workspace))


def project_domain(workspace: Path) -> Path:
    domain = workspace / "mywork" / "【Example】文档中心"
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\n"
        "name: Example\n"
        "domain_id: project-example\n"
        "domain_type: project-domain\n"
        "governance: project-docs\n"
        "moc: MOC-Example\n"
        "project_id: example\n"
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    return domain


def test_upsert_creates_profile_valid_project_document(workspace: Path) -> None:
    domain = project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).upsert(
        relative,
        document_type="plan",
        values={"description": "发布计划", "lifecycle": "proposed"},
        body="# 下一版\n",
        confirm=True,
    )
    assert result["status"] == "applied"
    parsed = parse_document((domain / "计划-下一版.md").read_text(encoding="utf-8"))
    assert parsed.frontmatter["project"] == "example"
    assert parsed.frontmatter["domain"] == "project-example"
    assert parsed.frontmatter["tags"] == []
    assert service(workspace).check(relative)["status"] == "ok"


def test_upsert_returns_all_missing_fields_without_writing(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/任务-示例.md"
    result = service(workspace).upsert(relative, document_type="task", confirm=True)
    assert result["status"] == "needs-input"
    required = {
        "description",
        "task_id",
        "lifecycle",
        "task_source",
        "assignee",
        "requires_human",
    }
    assert required <= set(result["missing_fields"])
    assert not (workspace / relative).exists()


def test_upsert_creates_task_without_skill_owned_enum_defaults(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/任务-示例.md"
    result = service(workspace).upsert(
        relative,
        document_type="task",
        values={
            "description": "验证任务创建",
            "task_id": "TASK-001",
            "lifecycle": "todo",
            "task_source": "assigned",
            "assignee": ["codex"],
            "requires_human": False,
        },
        confirm=True,
    )
    assert result["status"] == "applied"
    assert service(workspace).check(relative)["status"] == "ok"


def test_upsert_rejects_invalid_enum_before_writing(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).upsert(
        relative,
        document_type="plan",
        values={"description": "发布计划", "lifecycle": "wrong"},
        confirm=True,
    )
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "frontmatter-enum-invalid"
    assert not (workspace / relative).exists()


def test_upsert_rejects_explicit_unknown_field(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).upsert(
        relative,
        document_type="plan",
        values={"description": "发布计划", "lifecycle": "proposed", "typo": True},
        confirm=True,
    )
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "frontmatter-field-not-allowed"
    assert not (workspace / relative).exists()


def test_upsert_patch_preserves_body_and_rejects_stale_hash(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    target = workspace / relative
    document = service(workspace)
    document.upsert(
        relative,
        document_type="plan",
        values={"description": "发布计划", "lifecycle": "proposed"},
        body="# 原始正文\n",
        confirm=True,
    )
    preview = document.upsert(relative, values={"lifecycle": "maintained"})
    target.write_text(target.read_text(encoding="utf-8") + "\n外部修改\n", encoding="utf-8")
    stale = document.upsert(
        relative,
        values={"lifecycle": "maintained"},
        expected_hash=preview["expected_hash"],
        confirm=True,
    )
    assert stale["status"] == "blocked"
    assert stale["issues"][0]["code"] == "concurrent-change"
    assert "外部修改" in target.read_text(encoding="utf-8")


def test_upsert_appends_section_without_replacing_existing_body(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    document = service(workspace)
    document.upsert(
        relative,
        document_type="plan",
        values={"description": "发布计划", "lifecycle": "proposed"},
        body="# 原始正文\n",
        confirm=True,
    )
    result = document.upsert(
        relative,
        body="已完成设计",
        append_section="进展",
        confirm=True,
    )
    assert result["status"] == "applied"
    text = (workspace / relative).read_text(encoding="utf-8")
    assert "# 原始正文" in text
    assert "## 进展\n\n已完成设计" in text
