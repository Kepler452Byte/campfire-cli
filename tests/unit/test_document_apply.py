from __future__ import annotations

from pathlib import Path

import pytest

from campfire_cli.app.document.schema import DocumentApplyRequest
from campfire_cli.app.document.service.document_service import DocumentService
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.config.settings import WorkspaceSettings, campfire_home
from campfire_cli.container import AppContainer


def service(workspace: Path) -> DocumentService:
    return AppContainer.build("test").document


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
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    SqliteWorkspaceRepository(campfire_home()).save_project(
        ProjectEntry(
            id="example",
            workspace_id="test",
            name="Example",
            document_domain_id="project-example",
        )
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


def test_apply_derives_create_filename_from_type(workspace: Path) -> None:
    domain = project_domain(workspace)
    requested = "mywork/【Example】文档中心/下一版.md"

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=requested,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    assert result.status == "applied"
    assert result.action == "create"
    assert result.path == requested
    assert result.target == "mywork/【Example】文档中心/计划-下一版.md"
    assert not (workspace / requested).exists()
    assert (domain / "计划-下一版.md").is_file()
    assert [item.scope for item in result.follow_up] == ["mywork/【Example】文档中心"]


def test_apply_normalizes_missing_markdown_extension_and_type_prefix(
    workspace: Path,
) -> None:
    domain = project_domain(workspace)
    requested = "mywork/【Example】文档中心/下一版"

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=requested,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    assert result.target == "mywork/【Example】文档中心/计划-下一版.md"
    assert result.normalization == [
        {"reason": "markdown-extension", "required_suffix": ".md"},
        {
            "reason": "document-type-prefix",
            "document_type": "plan",
            "required_prefix": "计划-",
        },
    ]
    assert (domain / "计划-下一版.md").is_file()


def test_apply_rejects_non_markdown_extension_with_hint(workspace: Path) -> None:
    project_domain(workspace)

    with pytest.raises(ConfigurationError) as caught:
        service(workspace).apply(
            DocumentApplyRequest(
                path="mywork/【Example】文档中心/下一版.txt",
                document_type="plan",
            )
        )

    assert caught.value.payload()["code"] == "document-extension-invalid"
    assert caught.value.payload()["expected_suffix"] == ".md"
    assert "自动补充 .md" in caught.value.payload()["hint"]


def test_every_configured_type_derives_and_replaces_filename_prefix(workspace: Path) -> None:
    config = WorkspaceSettings.load("test", workspace).document_types

    for document_type, item in config["types"].items():
        prefix = item["prefix"]
        assert prefixed_name("标题.md", document_type, config) == f"{prefix}标题.md"
        assert prefixed_name("任务-标题.md", document_type, config) == f"{prefix}标题.md"


def test_apply_retypes_and_renames_one_document_atomically(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = domain / "任务-发布.md"
    source.write_text(
        "---\nname: 发布\ndescription: 发布任务\ntype: task\ntask_id: TASK-1\n"
        "project: example\ndomain: project-example\nstatus: current\nlifecycle: todo\n"
        "task_source: personal\nassignee: [agent]\nrequires_human: false\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# 发布\n",
        encoding="utf-8",
    )
    reference = domain / "记录-引用.md"
    reference.write_text("参考 [[任务-发布]]\n", encoding="utf-8")
    document = service(workspace)

    preview = document.apply(
        DocumentApplyRequest(
            path="mywork/【Example】文档中心/任务-发布.md",
            document_type="plan",
            values={"lifecycle": "proposed"},
        )
    )
    result = document.apply(
        DocumentApplyRequest(
            path=preview.path,
            document_type="plan",
            values={"lifecycle": "proposed"},
            expected_hash=preview.expected_hash,
            confirm=True,
        )
    )

    target = domain / "计划-发布.md"
    assert preview.status == "planned"
    assert preview.action == "retype"
    assert preview.target == "mywork/【Example】文档中心/计划-发布.md"
    assert result.status == "applied"
    assert not source.exists()
    assert parse_document(target.read_text(encoding="utf-8")).frontmatter["type"] == "plan"
    assert "[[计划-发布]]" in reference.read_text(encoding="utf-8")
    assert result.updated_references == ["mywork/【Example】文档中心/记录-引用.md"]


def test_apply_retypes_issue_to_record(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = domain / "问题-发布.md"
    source.write_text(
        "---\nname: 发布\ndescription: 发布问题\ntype: issue\n"
        "project: example\ndomain: project-example\nstatus: current\n"
        "lifecycle: proposed\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
        "tags: []\n---\n# 发布\n",
        encoding="utf-8",
    )

    result = service(workspace).apply(
        DocumentApplyRequest(
            path="mywork/【Example】文档中心/问题-发布.md",
            document_type="record",
            confirm=True,
        )
    )

    target = domain / "记录-发布.md"
    assert result.status == "applied"
    assert result.target == "mywork/【Example】文档中心/记录-发布.md"
    assert not source.exists()
    assert parse_document(target.read_text(encoding="utf-8")).frontmatter["type"] == "record"


def test_apply_retype_rejects_stale_source_hash(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = domain / "问题-发布.md"
    source.write_text(
        "---\nname: 发布\ndescription: 发布问题\ntype: issue\n"
        "project: example\ndomain: project-example\nstatus: current\n"
        "lifecycle: proposed\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
        "tags: []\n---\n# 发布\n",
        encoding="utf-8",
    )
    document = service(workspace)
    preview = document.apply(
        DocumentApplyRequest(
            path="mywork/【Example】文档中心/问题-发布.md",
            document_type="record",
        )
    )
    source.write_text(source.read_text(encoding="utf-8") + "外部变化\n", encoding="utf-8")

    result = document.apply(
        DocumentApplyRequest(
            path=preview.path,
            document_type="record",
            expected_hash=preview.expected_hash,
            confirm=True,
        )
    )

    assert result.status == "blocked"
    assert result.issues[0]["code"] == "concurrent-change"
    assert source.is_file()
    assert not (domain / "记录-发布.md").exists()


def test_apply_retype_requires_target_profile_fields_before_moving(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = domain / "知识-发布.md"
    source.write_text(
        "---\nname: 发布\ndescription: 发布知识\ntype: knowledge\n"
        "project: example\ndomain: project-example\nstatus: current\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# 发布\n",
        encoding="utf-8",
    )

    result = service(workspace).apply(
        DocumentApplyRequest(
            path="mywork/【Example】文档中心/知识-发布.md",
            document_type="task",
            confirm=True,
        )
    )

    assert result.status == "needs-input"
    assert result.action == "retype"
    assert result.target == "mywork/【Example】文档中心/任务-发布.md"
    assert {
        "task_id",
        "lifecycle",
        "task_source",
        "assignee",
        "requires_human",
    } <= set(result.missing_fields)
    assert source.is_file()
    assert not (domain / "任务-发布.md").exists()
    assert result.follow_up == []


def test_apply_retype_blocks_existing_target_without_writing(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = domain / "任务-发布.md"
    source.write_text(
        "---\nname: 发布\ndescription: 发布任务\ntype: task\ntask_id: TASK-1\n"
        "project: example\ndomain: project-example\nstatus: current\nlifecycle: todo\n"
        "task_source: personal\nassignee: [agent]\nrequires_human: false\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntags: []\n---\n# 发布任务\n",
        encoding="utf-8",
    )
    target = domain / "计划-发布.md"
    target.write_text("目标内容不能覆盖\n", encoding="utf-8")

    result = service(workspace).apply(
        DocumentApplyRequest(
            path="mywork/【Example】文档中心/任务-发布.md",
            document_type="plan",
            values={"lifecycle": "proposed"},
            confirm=True,
        )
    )

    assert result.status == "blocked"
    assert result.issues[0]["code"] == "target-exists"
    assert source.is_file()
    assert target.read_text(encoding="utf-8") == "目标内容不能覆盖\n"
    assert result.follow_up == []


def test_apply_rejects_type_inside_set_values(workspace: Path) -> None:
    project_domain(workspace)

    with pytest.raises(GovernanceBlockedError, match="只能通过 --type"):
        service(workspace).apply(
            DocumentApplyRequest(
                path="mywork/【Example】文档中心/计划-发布.md",
                document_type="plan",
                values={"type": "task"},
            )
        )


def test_apply_preview_does_not_return_actionable_follow_up(workspace: Path) -> None:
    project_domain(workspace)
    result = service(workspace).apply(
        DocumentApplyRequest(
            path="mywork/【Example】文档中心/计划-预览.md",
            document_type="plan",
            values={"description": "只预览", "lifecycle": "proposed"},
        )
    )

    assert result.status == "planned"
    assert result.write_performed is False
    assert result.follow_up == []


def test_apply_adopts_existing_body_without_frontmatter_in_one_write(workspace: Path) -> None:
    domain = project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-既有正文.md"
    target = domain / "计划-既有正文.md"
    body = "# 既有正文\n\n不能丢失。\n"
    target.write_text(body, encoding="utf-8")

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "接管既有正文", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    assert result.status == "applied"
    assert result.write_performed is True
    assert result.follow_up[0].command == "maintenance sync"
    parsed = parse_document(target.read_text(encoding="utf-8"))
    assert parsed.body == body
    assert parsed.frontmatter["project"] == "example"


def test_apply_skips_maintenance_when_only_non_derived_metadata_changes(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-快速更新.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "初始描述", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    result = document.apply(
        DocumentApplyRequest(
            path=relative,
            values={"description": "仅更新描述"},
            confirm=True,
        )
    )

    assert result.status == "applied"
    assert result.follow_up == []


def test_apply_inherits_project_through_nested_domain(workspace: Path) -> None:
    parent = project_domain(workspace)
    child = parent / "发布"
    child.mkdir()
    (child / "_领域.md").write_text(
        "---\nname: 发布\ndomain_id: project-example-release\n"
        "domain_type: project-domain\ngovernance: project-docs\n"
        "moc: MOC-发布\nparent_domain: project-example\nstatus: active\n---\n",
        encoding="utf-8",
    )
    relative = "mywork/【Example】文档中心/发布/计划-版本.md"

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "版本计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    assert result.status == "applied"
    parsed = parse_document((workspace / relative).read_text(encoding="utf-8"))
    assert parsed.frontmatter["domain"] == "project-example-release"
    assert parsed.frontmatter["project"] == "example"


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
    relative = "mywork/【Example】文档中心/示例.md"
    target = f"mywork/【Example】文档中心/{prefix}示例.md"

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
    assert result.target == target
    assert service(workspace).check(target)["status"] == "ok"


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
    assert all("argument_example" not in issue for issue in result.issues)
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
                "task_id": "001",
                "lifecycle": "todo",
                "task_source": "assigned",
                "assignee": '["codex"]',
                "requires_human": "false",
                "due": "2026-09-15",
            },
            confirm=True,
        )
    )
    assert result.status == "applied"
    parsed = parse_document((workspace / relative).read_text(encoding="utf-8"))
    assert parsed.frontmatter["task_id"] == "001"
    assert parsed.frontmatter["assignee"] == ["codex"]
    assert parsed.frontmatter["requires_human"] is False
    assert str(parsed.frontmatter["due"]) == "2026-09-15"
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
                "assignee": '["codex"]',
                "requires_human": "no",
            },
            confirm=True,
        )
    )

    assert result.status == "blocked"
    issue = next(item for item in result.issues if item["code"] == "frontmatter-type-invalid")
    assert issue["field"] == "requires_human"
    assert issue["allowed"] == ["boolean"]
    assert issue["argument_example"] == {"--set": "requires_human=true"}
    assert not (workspace / relative).exists()


def test_apply_rejects_non_json_list_with_direct_retry_example(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/知识-示例.md"

    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="knowledge",
            values={"description": "验证列表输入", "tags": "campfire,cli"},
            confirm=True,
        )
    )

    assert result.status == "blocked"
    assert result.issues == [
        {
            "code": "frontmatter-list-invalid",
            "path": relative,
            "detail": "tags",
            "field": "tags",
            "actual": "campfire,cli",
            "expected_type": "list",
            "allowed": ["list"],
            "argument_example": {"--set": 'tags=["item1","item2"]'},
        }
    ]
    assert not (workspace / relative).exists()


def test_apply_rejects_explicit_unknown_field(workspace: Path) -> None:
    project_domain(workspace)
    relative = "mywork/【Example】文档中心/计划-下一版.md"
    result = service(workspace).apply(
        DocumentApplyRequest(
            path=relative,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed", "typo": "true"},
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

    preview = document.move(source, "project-example", name="计划-新名称.md")
    assert preview.follow_up == []
    result = document.move(
        source,
        "project-example",
        name="计划-新名称.md",
        expected_hash=preview.expected_hash,
        confirm=True,
    )

    assert not result.issues, result.issues
    assert result.status == "moved"
    assert not (workspace / source).exists()
    assert (workspace / target).is_file()
    assert "[[计划-新名称]]" in reference.read_text(encoding="utf-8")
    assert "(计划-新名称.md)" in reference.read_text(encoding="utf-8")


def test_move_same_domain_preserves_frontmatter_bytes(workspace: Path) -> None:
    domain = project_domain(workspace)
    source = domain / "计划-保留注释.md"
    original = (
        "---\n"
        "name: 保留注释 # inline comment\n"
        "description: 发布计划\n"
        "type: plan\n"
        "project: example\n"
        "domain: project-example\n"
        "status: draft\n"
        "lifecycle: proposed\n"
        "created: 2026-09-15\n"
        "updated: '2026-09-15'\n"
        "tags: []\n"
        "---\n"
        "# 保留注释\n"
    )
    source.write_text(original, encoding="utf-8")

    result = service(workspace).move(
        "mywork/【Example】文档中心/计划-保留注释.md",
        "project-example",
        name="计划-仍保留注释.md",
        confirm=True,
    )

    assert result.status == "moved"
    assert (domain / "计划-仍保留注释.md").read_text(encoding="utf-8") == original


def test_move_crosses_domains_and_updates_structural_frontmatter(workspace: Path) -> None:
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

    target = "mywork/另一个领域/计划-旧名称.md"
    preview = document.move(source, "other")
    assert preview.follow_up == []
    result = document.move(source, "other", expected_hash=preview.expected_hash, confirm=True)

    assert result.status == "moved"
    assert result.source_domain == "project-example"
    assert result.target_domain == "other"
    assert result.profile == "base"
    assert result.frontmatter_changes["domain"] == "other"
    assert result.frontmatter_changes["project"] is None
    assert not (workspace / source).exists()
    moved = parse_document((workspace / target).read_text(encoding="utf-8"))
    assert moved.frontmatter["domain"] == "other"
    assert "project" not in moved.frontmatter
    assert [item.scope for item in result.follow_up] == ["mywork"]


def test_move_resolves_a_nested_target_domain_by_id(workspace: Path) -> None:
    root = project_domain(workspace)
    nested = root / "发布"
    nested.mkdir()
    (nested / "_领域.md").write_text(
        "---\nname: 发布\ndomain_id: project-example-release\n"
        "domain_type: project-domain\ngovernance: project-docs\n"
        "moc: MOC-发布\nparent_domain: project-example\nproject_id: example\n"
        "status: active\n---\n",
        encoding="utf-8",
    )
    source = "mywork/【Example】文档中心/计划-版本.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    result = document.move(source, "project-example-release", confirm=True)

    assert result.status == "moved"
    target = nested / "计划-版本.md"
    assert target.is_file()
    parsed = parse_document(target.read_text(encoding="utf-8"))
    assert parsed.frontmatter["domain"] == "project-example-release"
    assert parsed.frontmatter["project"] == "example"


def test_move_cross_domain_returns_all_missing_target_profile_fields(workspace: Path) -> None:
    project_domain(workspace)
    other = workspace / "mywork" / "另一个领域"
    other.mkdir()
    (other / "_领域.md").write_text(
        "---\nname: Other\ndomain_id: other\ndomain_type: work-domain\n"
        "governance: work-docs\nmoc: MOC-Other\nstatus: active\n---\n",
        encoding="utf-8",
    )
    source = other / "计划-迁入项目.md"
    source.write_text(
        "---\nname: 迁入项目\ndescription: 示例\ntype: plan\n"
        "domain: other\nstatus: draft\ncreated: 2026-09-15\nupdated: 2026-09-15\n"
        "tags: []\n---\n# 迁入项目\n",
        encoding="utf-8",
    )
    document = service(workspace)
    source_name = "mywork/另一个领域/计划-迁入项目.md"
    target_name = "mywork/【Example】文档中心/计划-迁入项目.md"

    blocked = document.move(source_name, "project-example", confirm=True)

    assert blocked.status == "needs-input"
    assert blocked.missing_fields == ["lifecycle"]
    assert blocked.issues[0]["allowed"] == [
        "maintained",
        "proposed",
        "completed",
        "archived",
    ]
    assert source.is_file()

    moved = document.move(
        source_name,
        "project-example",
        values={"lifecycle": "proposed"},
        expected_hash=blocked.expected_hash,
        confirm=True,
    )

    assert moved.status == "moved"
    parsed = parse_document((workspace / target_name).read_text(encoding="utf-8"))
    assert parsed.frontmatter["project"] == "example"
    assert parsed.frontmatter["domain"] == "project-example"
    assert parsed.frontmatter["lifecycle"] == "proposed"


def test_move_rejects_new_field_outside_target_profile(workspace: Path) -> None:
    project_domain(workspace)
    source = "mywork/【Example】文档中心/计划-未知字段.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    result = document.move(
        source,
        "project-example",
        name="计划-新名称.md",
        values={"invented": "value"},
        confirm=True,
    )

    assert result.status == "blocked"
    assert result.issues == [
        {
            "code": "frontmatter-field-not-allowed",
            "path": "mywork/【Example】文档中心/计划-新名称.md",
            "field": "invented",
        }
    ]
    assert (workspace / source).is_file()


def test_move_uses_the_same_profile_driven_value_decoder(workspace: Path) -> None:
    project_domain(workspace)
    source = "mywork/【Example】文档中心/任务-旧名称.md"
    target = "mywork/【Example】文档中心/任务-新名称.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="task",
            values={
                "description": "移动任务",
                "task_id": "001",
                "lifecycle": "todo",
                "task_source": "assigned",
                "assignee": '["codex"]',
                "requires_human": "false",
            },
            confirm=True,
        )
    )

    preview = document.move(
        source,
        "project-example",
        name="任务-新名称.md",
        values={"assignee": '["human"]', "requires_human": "true"},
    )
    result = document.move(
        source,
        "project-example",
        name="任务-新名称.md",
        values={"assignee": '["human"]', "requires_human": "true"},
        expected_hash=preview.expected_hash,
        confirm=True,
    )

    assert result.status == "moved"
    parsed = parse_document((workspace / target).read_text(encoding="utf-8"))
    assert parsed.frontmatter["task_id"] == "001"
    assert parsed.frontmatter["assignee"] == ["human"]
    assert parsed.frontmatter["requires_human"] is True


def test_move_rejects_target_name_with_directory_components(workspace: Path) -> None:
    project_domain(workspace)
    source = "mywork/【Example】文档中心/计划-旧位置.md"
    document = service(workspace)
    document.apply(
        DocumentApplyRequest(
            path=source,
            document_type="plan",
            values={"description": "发布计划", "lifecycle": "proposed"},
            confirm=True,
        )
    )

    with pytest.raises(ConfigurationError, match="--name 必须是 Markdown 文件名"):
        document.move(source, "project-example", name="历史/计划-旧位置.md")
