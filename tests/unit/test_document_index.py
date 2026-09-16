from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from campfire_cli.app.workspace.repository.workspace_repository import (
    SqliteWorkspaceRepository,
)
from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer


def write_project_domain(workspace: Path) -> Path:
    domain = workspace / "mywork/Project"
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\n"
        "name: Project\n"
        "domain_id: project-example\n"
        "domain_type: project-domain\n"
        "governance: project-docs\n"
        "moc: MOC-Project\n"
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
    (domain / "MOC-Project.md").write_text(
        "---\nname: Project\ndescription: Index\ntype: moc\ndocument_status: current\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n---\n# Project\n",
        encoding="utf-8",
    )
    return domain


def write_task(path: Path, name: str, task_status: str, body: str = "") -> None:
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {name}\n"
        "type: task\n"
        "document_status: current\n"
        f"task_status: {task_status}\n"
        "priority: medium\n"
        "created: 2026-09-15\n"
        "updated: 2026-09-15\n"
        "tags: []\n"
        "---\n"
        f"# {name}\n{body}",
        encoding="utf-8",
    )


def test_list_uses_reconciled_index_and_keeps_all_task_lifecycles(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    todo = domain / "任务-Todo.md"
    done = domain / "任务-Done.md"
    write_task(todo, "Todo", "todo")
    write_task(done, "Done", "completed")
    document = AppContainer.build("test").document

    all_tasks = document.list(document_type="task")

    assert all_tasks.count == 2
    assert [item.name for item in all_tasks.items] == ["Done", "Todo"]
    assert {item.task_status for item in all_tasks.items} == {"todo", "completed"}
    assert all(item.project == "example" for item in all_tasks.items)
    assert all_tasks.items[0].updated == "2026-09-15"

    write_task(todo, "Todo", "blocked")
    blocked = document.list(project="example", document_type="task", task_status="blocked")

    assert blocked.count == 1
    assert blocked.items[0].name == "Todo"
    assert blocked.items[0].task_status == "blocked"
    assert blocked.index_generation > all_tasks.index_generation


def test_inspect_returns_declared_outgoing_incoming_and_unresolved(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    source = domain / "计划-Source.md"
    target = domain / "记录-Target.md"
    incoming = domain / "记录-Incoming.md"
    source.write_text(
        "---\nname: Source\ndescription: Source\ntype: plan\nproject: example\n"
        "domain: project-example\ndocument_status: current\nlifecycle: proposed\n"
        "related: [记录-Target]\ncreated: 2026-09-15\nupdated: 2026-09-15\ntags: []\n"
        "---\n# Source\nSee [[记录-Target]] and [[Missing]].\n",
        encoding="utf-8",
    )
    target.write_text(
        "---\nname: Target\ndescription: Target\ntype: record\nproject: example\n"
        "domain: project-example\ndocument_status: current\nlifecycle: maintained\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n"
        "---\n# Target\n",
        encoding="utf-8",
    )
    incoming.write_text(
        "---\nname: Incoming\ndescription: Incoming\ntype: record\nproject: example\n"
        "domain: project-example\ndocument_status: current\nlifecycle: maintained\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n"
        "---\n# Incoming\nSee [[计划-Source]].\n",
        encoding="utf-8",
    )
    document = AppContainer.build("test").document

    result = document.inspect("mywork/Project/计划-Source.md")

    assert result["status"] == "needs-review"
    assert [item["name"] for item in result["relations"]["declared"]] == ["Target"]
    assert [item["name"] for item in result["relations"]["outgoing"]] == ["Target"]
    assert [item["name"] for item in result["relations"]["incoming"]] == ["Incoming"]
    assert result["relations"]["unresolved"][0]["raw_target"] == "Missing"
    assert any(item["code"] == "document-reference-missing" for item in result["issues"])


def test_reconcile_removes_deleted_documents_and_edges(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    source = domain / "记录-Source.md"
    target = domain / "记录-Target.md"
    for path, name, body in (
        (source, "Source", "See [[记录-Target]].\n"),
        (target, "Target", ""),
    ):
        path.write_text(
            "---\n"
            f"name: {name}\ndescription: {name}\ntype: record\nproject: example\n"
            "domain: project-example\ndocument_status: current\nlifecycle: maintained\n"
            "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n"
            "---\n"
            f"# {name}\n{body}",
            encoding="utf-8",
        )
    document = AppContainer.build("test").document
    assert document.inspect("mywork/Project/记录-Source.md")["relations"]["outgoing"]

    target.unlink()
    result = document.inspect("mywork/Project/记录-Source.md")

    assert result["relations"]["outgoing"] == []
    assert result["relations"]["unresolved"][0]["raw_target"] == "记录-Target"


def test_reconcile_rebuilds_when_domain_context_changes(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    task = domain / "任务-Todo.md"
    write_task(task, "Todo", "todo")
    document = AppContainer.build("test").document
    initial = document.list(project="example", document_type="task")

    marker = domain / "_领域.md"
    marker.write_text(
        marker.read_text(encoding="utf-8").replace(
            "domain_id: project-example", "domain_id: project-renamed"
        ),
        encoding="utf-8",
    )
    updated = document.list(domain="project-renamed", document_type="task")

    assert updated.count == 1
    assert updated.items[0].domain == "project-renamed"
    assert updated.index_generation > initial.index_generation


def test_reconcile_removes_edges_when_target_becomes_non_queryable(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    source = domain / "记录-Source.md"
    target = domain / "记录-Target.md"
    source.write_text(
        "---\nname: Source\ndescription: Source\ntype: record\nproject: example\n"
        "domain: project-example\ndocument_status: current\nlifecycle: maintained\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n"
        "---\n# Source\nSee [[记录-Target]].\n",
        encoding="utf-8",
    )
    target.write_text(
        "---\nname: Target\ndescription: Target\ntype: record\nproject: example\n"
        "domain: project-example\ndocument_status: current\nlifecycle: maintained\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n---\n# Target\n",
        encoding="utf-8",
    )
    document = AppContainer.build("test").document
    assert document.inspect("mywork/Project/记录-Source.md")["relations"]["outgoing"]

    target.write_text(
        target.read_text(encoding="utf-8").replace("type: record", "type: moc"),
        encoding="utf-8",
    )
    result = document.inspect("mywork/Project/记录-Source.md")

    assert result["relations"]["outgoing"] == []
    assert result["relations"]["unresolved"][0]["raw_target"] == "记录-Target"


def test_list_rejects_unknown_structured_filters(workspace: Path) -> None:
    write_project_domain(workspace)
    document = AppContainer.build("test").document

    with pytest.raises(ConfigurationError, match="未知 Project"):
        document.list(project="missing")
    with pytest.raises(ConfigurationError, match="未知 Domain"):
        document.list(domain="missing")


def test_index_excludes_moc_and_reports_ambiguous_links(workspace: Path) -> None:
    first = write_project_domain(workspace)
    second = workspace / "mynote/Knowledge"
    second.mkdir()
    (second / "_领域.md").write_text(
        "---\nname: Knowledge\ndomain_id: knowledge\ndomain_type: knowledge-domain\n"
        "governance: knowledge-docs\nmoc: MOC-Knowledge\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (second / "MOC-Knowledge.md").write_text(
        "---\nname: Knowledge\ndescription: Index\ntype: moc\ndocument_status: current\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n---\n# Knowledge\n",
        encoding="utf-8",
    )
    for directory in (first, second):
        target = directory / "记录-Shared.md"
        target.write_text(
            "---\nname: Shared\ndescription: Shared\ntype: record\ndocument_status: current\n"
            "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n---\n# Shared\n",
            encoding="utf-8",
        )
    source = first / "记录-Source.md"
    source.write_text(
        "---\nname: Source\ndescription: Source\ntype: record\ndocument_status: current\n"
        "created: 2026-09-15\nupdated: 2026-09-15\ntags: []\n"
        "---\n# Source\nSee [[记录-Shared]].\n",
        encoding="utf-8",
    )
    document = AppContainer.build("test").document

    listed = document.list()
    inspected = document.inspect("mywork/Project/记录-Source.md")

    assert all(item.type != "moc" for item in listed.items)
    unresolved = inspected["relations"]["unresolved"][0]
    assert unresolved["resolution"] == "ambiguous"
    assert unresolved["candidates"] == [
        "mynote/Knowledge/记录-Shared.md",
        "mywork/Project/记录-Shared.md",
    ]


def test_effective_config_change_forces_full_rebuild(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    write_task(domain / "任务-Todo.md", "Todo", "todo")
    initial = AppContainer.build("test").document.list(document_type="task")
    config = workspace / "_campfire/config.yml"
    config.write_text(
        "version: 1\nfrontmatter_schema:\n  profiles:\n    base:\n      unknown_fields: report\n",
        encoding="utf-8",
    )

    rebuilt = AppContainer.build("test").document.list(document_type="task")

    assert rebuilt.count == initial.count
    assert rebuilt.index_generation > initial.index_generation


def test_failed_snapshot_replace_keeps_previous_generation(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    task = domain / "任务-Todo.md"
    write_task(task, "Todo", "todo")
    document = AppContainer.build("test").document
    initial = document.list(document_type="task")
    database = workspace / "_campfire/campfire.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create trigger reject_document_snapshot before insert on documents "
            "begin select raise(abort, 'rejected test snapshot'); end"
        )
    write_task(task, "Todo", "blocked")

    with pytest.raises(IntegrityError, match="rejected test snapshot"):
        document.list(document_type="task")

    with sqlite3.connect(database) as connection:
        generation = connection.execute(
            "select generation from document_index_state where workspace_id = 'test'"
        ).fetchone()
        task_status = connection.execute(
            "select task_status from documents where workspace_id = 'test' "
            "and path = 'mywork/Project/任务-Todo.md'"
        ).fetchone()
        connection.execute("drop trigger reject_document_snapshot")
    recovered = document.list(document_type="task")

    assert generation == (initial.index_generation,)
    assert task_status == ("todo",)
    assert recovered.items[0].task_status == "blocked"
    assert recovered.index_generation > initial.index_generation


def test_project_registry_root_supplies_legacy_domain_context(workspace: Path) -> None:
    domain = workspace / "mywork/Legacy"
    domain.mkdir()
    (domain / "_领域.md").write_text(
        "---\nname: Legacy\ndomain_id: project-legacy\n"
        "domain_type: project-domain\ngovernance: project-docs\n"
        "moc: MOC-Legacy\nstatus: active\n---\n",
        encoding="utf-8",
    )
    write_task(domain / "任务-Todo.md", "Todo", "todo")
    registry = SqliteWorkspaceRepository(workspace / "_campfire")
    registry.save_project(
        ProjectEntry(
            id="legacy",
            workspace_id="test",
            name="Legacy",
            document_domain_id="project-legacy",
        )
    )

    result = AppContainer.build("test").document.list(project="legacy")

    assert result.count == 1
    assert result.items[0].project == "legacy"
