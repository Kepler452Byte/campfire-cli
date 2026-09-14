from __future__ import annotations

from pathlib import Path

import pytest

from campfire_cli.app.document.schema import DocumentApplyRequest
from campfire_cli.app.document.service.document_service import DocumentService
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import GovernanceBlockedError
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


def test_apply_creates_profile_valid_project_document(workspace: Path) -> None:
    domain = project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            body="# 下一版\n",
            confirm=True,
        )
    )
    assert not result.issues, result.issues
    assert result.status == "applied"
    parsed = parse_document((domain / "计划-下一版.md").read_text(encoding="utf-8"))
    assert parsed.frontmatter["project"] == "example"
    assert parsed.frontmatter["domain"] == "project-example"
    assert parsed.frontmatter["tags"] == []
    assert service(workspace).check(relative)["status"] == "ok"


@pytest.mark.parametrize(
    ("document_type", "prefix", "values"),
    [
        ("decision", "决策-", {"description": "决策", "lifecycle": "proposed"}),
        ("requirement-doc", "需求-", {"description": "需求"}),
        ("issue", "问题-", {"description": "问题", "lifecycle": "proposed"}),
        ("record", "记录-", {"description": "记录", "lifecycle": "proposed"}),
        ("knowledge", "知识-", {"description": "知识"}),
    ],
)
def test_apply_creates_all_golden_path_document_types(
    workspace: Path,
    document_type: str,
    prefix: str,
    values: dict[str, str],
) -> None:
    project_domain(workspace)
    relative = f"mywork/【Example】文档中心/{prefix}示例.md"

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type=document_type,
            values=values,
            confirm=True,
        )
    )

    assert not result.issues, result.issues
    assert result.status == "applied"
    assert service(workspace).check(relative)["status"] == "ok"


def test_apply_returns_all_missing_fields_without_writing(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/任务-示例.md"
    result = service(workspace).apply(
        DocumentApplyRequest(path=relative, document_type="task", confirm=True)
    )
    assert result.status == "needs-input"
    required = {
        "description",
        "task_id",
        "lifecycle",
        "task_source",
        "assignee",
        "requires_human",
    }
    assert required <= set(result.missing_fields)
    constraints = {item.get("field"): item.get("allowed") for item in result.issues}
    assert constraints["lifecycle"] == [
        "todo",
        "in-progress",
        "blocked",
        "review",
        "completed",
        "cancelled",
        "archived",
    ]
    assert constraints["assignee"] == ["list"]
    assert constraints["requires_human"] == ["boolean"]
    assert not (workspace / relative).exists()


def test_apply_creates_task_without_skill_owned_enum_defaults(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/任务-示例.md"
    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
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
    )
    assert result.status == "applied"
    assert service(workspace).check(relative)["status"] == "ok"


def test_apply_rejects_invalid_enum_before_writing(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "wrong"},
            confirm=True,
        )
    )
    assert result.status == "blocked"
    assert result.issues[0]["code"] == "frontmatter-enum-invalid"
    assert not (workspace / relative).exists()


def test_apply_rejects_invalid_scalar_type_before_writing(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/任务-示例.md"

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="task",
            values={
                "description": "验证任务创建",
                "task_id": "TASK-001",
                "lifecycle": "todo",
                "task_source": "assigned",
                "assignee": ["codex"],
                "requires_human": "false",
            },
            confirm=True,
        )
    )

    assert result.status == "blocked"
    issue = next(item for item in result.issues if item["code"] == "frontmatter-type-invalid")
    assert issue["field"] == "requires_human"
    assert issue["allowed"] == ["boolean"]
    assert not (workspace / relative).exists()


def test_apply_rejects_explicit_unknown_field(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed", "typo": True},
            confirm=True,
        )
    )
    assert result.status == "blocked"
    assert result.issues[0]["code"] == "frontmatter-field-not-allowed"
    assert not (workspace / relative).exists()


def test_apply_rejects_project_or_domain_that_conflicts_with_target(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"

    with pytest.raises(GovernanceBlockedError, match="Domain 上下文不一致"):
        service(workspace).apply(
            DocumentApplyRequest(
                path=relative,
                document_type="plan",
                values={
                    "description": "发布计划",
                    "lifecycle": "proposed",
                    "project": "another-project",
                },
                confirm=True,
            )
        )

    assert not (workspace / relative).exists()


def test_apply_patch_preserves_body_and_rejects_stale_hash(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    target = workspace / relative
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            body="# 原始正文\n",
            confirm=True,
        )
    )
    preview = document.apply(
        DocumentApplyRequest(path=relative, values={"lifecycle": "maintained"})
    )
    target.write_text(target.read_text(encoding="utf-8") + "\n外部修改\n", encoding="utf-8")
    stale = document.apply(
        DocumentApplyRequest(
            path=relative,
            values={"lifecycle": "maintained"},
            expected_hash=preview.expected_hash,
            confirm=True,
        )
    )
    assert stale.status == "blocked"
    assert stale.issues[0]["code"] == "concurrent-change"
    assert "外部修改" in target.read_text(encoding="utf-8")


def test_apply_patch_preserves_untouched_frontmatter_blocks(workspace: Path) -> None:
    domain = project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    target = domain / "计划-下一版.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )
    original = target.read_text(encoding="utf-8").replace(
        "description: 发布计划", "description: 发布计划 # 保留注释"
    )
    target.write_text(original, encoding="utf-8")

    result = document.apply(
        DocumentApplyRequest(
            path=relative,
            values={"lifecycle": "maintained"},
            confirm=True,
        )
    )

    assert result.status == "applied"
    assert "description: 发布计划 # 保留注释" in target.read_text(encoding="utf-8")


def test_apply_appends_section_without_replacing_existing_body(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            body="# 原始正文\n",
            confirm=True,
        )
    )
    result = document.apply(
        DocumentApplyRequest(
            path=relative,
            body="已完成设计",
            append_section="进展",
            confirm=True,
        )
    )
    assert result.status == "applied"
    text = (workspace / relative).read_text(encoding="utf-8")
    assert "# 原始正文" in text
    assert "## 进展\n\n已完成设计" in text


def test_move_renames_document_and_updates_references(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = "mywork/【Example】文档中心/计划-旧名称.md"
    target = "mywork/【Example】文档中心/计划-新名称.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            body="# 旧名称\n",
            confirm=True,
        )
    )
    reference = domain / "记录-引用.md"
    reference.write_text("[[计划-旧名称]]\n[计划](计划-旧名称.md)\n", encoding="utf-8")

    preview = document.move(source, target)
    result = document.move(source, target, expected_hash=preview.expected_hash, confirm=True)

    assert not result.issues, result.issues
    assert result.status == "moved"
    assert not (workspace / source).exists()
    assert (workspace / target).is_file()
    assert "[[计划-新名称]]" in reference.read_text(encoding="utf-8")
    assert "(计划-新名称.md)" in reference.read_text(encoding="utf-8")


def test_move_blocks_cross_domain_changes(workspace: Path) -> None:
    project_domain(workspace)
    other = workspace / "mywork" / "另一个领域"
    other.mkdir()
    (other / "_领域.md").write_text(
        "---\nname: Other\ndomain_id: other\ndomain_type: work-domain\n"
        "governance: work-docs\nmoc: MOC-Other\nstatus: active\n---\n",
        encoding="utf-8",
    )
    source = "mywork/【Example】文档中心/计划-旧名称.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    result = document.move(source, "mywork/另一个领域/计划-旧名称.md", confirm=True)

    assert result.status == "blocked"
    assert result.issues[0]["code"] == "cross-domain-move"
    assert (workspace / source).is_file()


def test_move_rebases_relative_links_when_relocating_inside_domain(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = "mywork/【Example】文档中心/计划-旧位置.md"
    target = "mywork/【Example】文档中心/历史/计划-旧位置.md"
    related = domain / "记录-依据.md"
    related.write_text("依据\n", encoding="utf-8")
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            body="[依据](记录-依据.md)\n",
            confirm=True,
        )
    )

    result = document.move(source, target, confirm=True)

    assert not result.issues, result.issues
    assert result.status == "moved"
    moved = (workspace / target).read_text(encoding="utf-8")
    assert "[依据](../记录-依据.md)" in moved
