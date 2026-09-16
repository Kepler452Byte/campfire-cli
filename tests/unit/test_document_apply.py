from __future__ import annotations

from pathlib import Path

from campfire_cli.app.document.schema import DocumentApplyRequest
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
