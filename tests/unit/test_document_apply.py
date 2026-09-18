from __future__ import annotations

from pathlib import Path

from campfire_cli.app.document.repository.document_profile_repository import (
    DocumentProfileRepository,
)
from campfire_cli.app.document.schema import DocumentApplyRequest
from campfire_cli.app.document.service.document_profile_service import DocumentProfileService
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer


def project_domain(workspace: Path) -> Path:
    domain = workspace / "mywork" / "Example"
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\nname: Example\ndomain_id: project-example\ndomain_type: project-domain\n"
        "governance: project-docs\nmoc: MOC-Example\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (workspace / ".campfire.yaml").write_text(
        "schema_version: 1\nworkspace:\n  id: test\n  name: Test\n"
        "  governance_version: 1\nprojects:\n- id: example\n  name: Example\n"
        "  document_domain_id: project-example\n  status: active\n",
        encoding="utf-8",
    )
    SqliteWorkspaceRepository(campfire_home()).save_project(
        ProjectEntry(
            id="example", workspace_id="test", name="Example", document_domain_id="project-example"
        )
    )
    return domain


def test_apply_uses_base_profile_only(workspace: Path) -> None:
    domain = project_domain(workspace)
    result = AppContainer.build("test").document.apply(
        DocumentApplyRequest(
            path="mywork/Example/next",
            document_type="plan",
            values={"description": "发布计划"},
            confirm=True,
        )
    )
    assert result.status == "applied"
    document = parse_document((domain / "计划-next.md").read_text(encoding="utf-8"))
    assert set(document.frontmatter) == {
        "name",
        "description",
        "type",
        "document_status",
        "created",
        "updated",
        "tags",
    }


def test_apply_invalid_assignment_is_not_reported_as_missing(workspace: Path) -> None:
    project_domain(workspace)
    result = AppContainer.build("test").document.apply(
        DocumentApplyRequest(
            path="mywork/Example/bad",
            document_type="task",
            values={"task_status": "unknown", "created": "not-a-date"},
            confirm=True,
        )
    )
    assert result.status == "blocked"
    assert result.missing_fields == ["description"]
    assert {(issue["code"], issue["field"]) for issue in result.issues} == {
        ("frontmatter-enum-invalid", "task_status"),
        ("frontmatter-date-invalid", "created"),
        ("frontmatter-field-missing", "description"),
    }
    assert not result.write_performed


def test_apply_invalid_update_keeps_original(workspace: Path) -> None:
    project_domain(workspace)
    document = AppContainer.build("test").document
    created = document.apply(
        DocumentApplyRequest(
            path="mywork/Example/task",
            document_type="task",
            values={"description": "任务", "task_status": "todo"},
            confirm=True,
        )
    )
    path = workspace / created.target
    original = path.read_bytes()
    result = document.apply(
        DocumentApplyRequest(
            path=created.target,
            values={"description": "", "task_status": "invalid", "title": "wrong"},
            confirm=True,
        )
    )
    assert result.status == "blocked"
    assert result.missing_fields == ["description"]
    assert len(result.issues) == 3
    assert result.follow_up == []
    assert path.read_bytes() == original


def test_task_dynamic_project_value_is_validated_not_injected(workspace: Path) -> None:
    domain = project_domain(workspace)
    document = AppContainer.build("test").document
    accepted = document.apply(
        DocumentApplyRequest(
            path="mywork/Example/task",
            document_type="task",
            values={"description": "任务", "task_status": "todo", "related_project": "example"},
            confirm=True,
        )
    )
    assert accepted.status == "applied"
    assert (
        parse_document((domain / "任务-task.md").read_text(encoding="utf-8")).frontmatter[
            "related_project"
        ]
        == "example"
    )
    rejected = document.apply(
        DocumentApplyRequest(
            path="mywork/Example/bad",
            document_type="task",
            values={"description": "任务", "task_status": "todo", "related_project": "missing"},
        )
    )
    assert rejected.issues[0]["code"] == "frontmatter-enum-invalid"
    assert rejected.issues[0]["expected_type"] == "enum"
    assert rejected.issues[0]["allowed"] == ["example"]


def test_profile_candidates_and_defaults_are_consistent(workspace: Path) -> None:
    domain = project_domain(workspace)
    container = AppContainer.build("test")
    document = container.document
    task = document.apply(
        DocumentApplyRequest(
            path="mywork/Example/task",
            document_type="task",
            values={"description": "任务", "task_status": "todo"},
            confirm=True,
        )
    )
    plan = document.apply(
        DocumentApplyRequest(
            path="mywork/Example/plan",
            document_type="plan",
            values={"description": "计划"},
            confirm=True,
        )
    )
    assert task.status == plan.status == "applied"

    profiles = DocumentProfileService(
        "test",
        workspace,
        container.settings.document_types,
        DocumentProfileRepository(container.settings.state_root),
    )
    shown = profiles.show_profile("task")["profile"]
    resolved = profiles.resolve("mywork/Example/任务-task.md")["profile"]
    inspected = document.inspect("mywork/Example/任务-task.md")["profile"]
    for profile in (shown, resolved, inspected):
        assert profile["enums"]["related_project"] == ["example"]
        assert profile["enums"]["task_status"] == [
            "todo",
            "in-progress",
            "blocked",
            "completed",
            "cancelled",
        ]
    assert shown["defaults"]["document_status"] == "current"
    assert (
        parse_document((domain / "任务-task.md").read_text(encoding="utf-8")).frontmatter[
            "document_status"
        ]
        == "current"
    )
    assert (
        parse_document((domain / "计划-plan.md").read_text(encoding="utf-8")).frontmatter[
            "document_status"
        ]
        == "draft"
    )


def test_human_request_is_restricted_to_global_request_root(workspace: Path) -> None:
    document = AppContainer.build("test").document
    result = document.apply(
        DocumentApplyRequest(
            path="_待用户确认/上线目标",
            document_type="human-request",
            values={"description": "确认上线目标"},
            confirm=True,
        )
    )
    assert result.status == "applied"
    assert result.follow_up == []


def test_archived_document_does_not_require_an_archive_directory(workspace: Path) -> None:
    domain = project_domain(workspace)

    result = AppContainer.build("test").document.apply(
        DocumentApplyRequest(
            path="mywork/Example/已完成方案",
            document_type="plan",
            values={"description": "已完成的方案", "document_status": "archived"},
            confirm=True,
        )
    )

    assert result.status == "applied"
    document = parse_document((domain / "计划-已完成方案.md").read_text(encoding="utf-8"))
    assert document.frontmatter["document_status"] == "archived"


def test_rename_keeps_directory_and_updates_name_and_references(workspace: Path) -> None:
    domain = project_domain(workspace)
    document = AppContainer.build("test").document
    created = document.apply(
        DocumentApplyRequest(
            path="mywork/Example/notes/旧标题",
            document_type="record",
            values={"description": "重命名测试"},
            confirm=True,
        )
    )
    assert created.status == "applied"
    source = domain / "notes" / "记录-旧标题.md"
    reference = domain / "记录-引用.md"
    reference.write_text(
        "---\nname: 引用\ndescription: 引用测试\ntype: record\ndocument_status: draft\n"
        "created: '2026-09-17'\nupdated: '2026-09-17'\ntags: []\n---\n\n"
        "[[记录-旧标题]]\n[路径](notes/记录-旧标题.md)\n",
        encoding="utf-8",
    )

    planned = document.rename("mywork/Example/notes/记录-旧标题.md", "新标题")
    assert planned.status == "ready"
    assert planned.target == "mywork/Example/notes/记录-新标题.md"
    assert planned.frontmatter_changes["name"] == "新标题"

    applied = document.rename(
        "mywork/Example/notes/记录-旧标题.md",
        "新标题",
        expected_hash=planned.expected_hash,
        confirm=True,
    )
    target = domain / "notes" / "记录-新标题.md"
    assert applied.status == "renamed"
    assert applied.write_performed is True
    assert not source.exists()
    assert parse_document(target.read_text(encoding="utf-8")).frontmatter["name"] == "新标题"
    assert "[[记录-新标题]]" in reference.read_text(encoding="utf-8")
    assert "notes/记录-新标题.md" in reference.read_text(encoding="utf-8")


def test_rename_rejects_existing_target(workspace: Path) -> None:
    domain = project_domain(workspace)
    document = AppContainer.build("test").document
    for title in ("旧标题", "新标题"):
        result = document.apply(
            DocumentApplyRequest(
                path=f"mywork/Example/{title}",
                document_type="record",
                values={"description": title},
                confirm=True,
            )
        )
        assert result.status == "applied"

    result = document.rename("mywork/Example/记录-旧标题.md", "新标题")
    assert result.status == "blocked"
    assert result.issues == [{"code": "target-exists", "path": "mywork/Example/记录-新标题.md"}]
    assert (domain / "记录-旧标题.md").is_file()
