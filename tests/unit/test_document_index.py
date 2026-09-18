from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from campfire_cli.app.workspace.repository.workspace_repository import (
    SqliteWorkspaceRepository,
)
from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry
from campfire_cli.common.documents.markdown import render_document
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


def test_system_scope_is_indexed_without_a_domain(workspace: Path) -> None:
    request = workspace / "_待用户确认/待确认-发布.md"
    request.write_text(
        "---\n"
        "name: 发布\n"
        "description: 确认是否发布\n"
        "type: human-request\n"
        "document_status: current\n"
        "created: 2026-09-15\n"
        "updated: 2026-09-15\n"
        "tags: []\n"
        "human_decision_status: pending\n"
        "---\n# 发布\n",
        encoding="utf-8",
    )
    document = AppContainer.build("test").document

    listed = document.list(document_type="human-request")
    inspected = document.inspect("_待用户确认/待确认-发布.md")

    assert [item.path for item in listed.items] == ["_待用户确认/待确认-发布.md"]
    assert inspected["domain_id"] is None
    assert inspected["project_id"] is None
    assert inspected["status"] == "ok"


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


def test_list_rejects_unknown_structured_filters(workspace: Path) -> None:
    write_project_domain(workspace)
    document = AppContainer.build("test").document

    with pytest.raises(ConfigurationError, match="未知 Project"):
        document.list(project="missing")
    with pytest.raises(ConfigurationError, match="未知 Domain"):
        document.list(domain="missing")


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


def write_record(path: Path, root: Path, links: list[str] | None = None, body: str = "") -> None:
    path.write_text(
        render_document(
            {
                "name": path.stem.removeprefix("记录-"),
                "description": "关系测试",
                "type": "record",
                "document_status": "current",
                "created": "2026-09-18",
                "updated": "2026-09-18",
                "tags": [],
                **({"related_docs": links} if links is not None else {}),
            },
            body,
            [
                "name",
                "description",
                "type",
                "document_status",
                "created",
                "updated",
                "tags",
                "related_docs",
            ],
        ),
        encoding="utf-8",
    )


def test_only_related_docs_produces_edges_and_missing_is_reported(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    source, target, incoming = [
        domain / f"记录-{name}.md" for name in ("Source", "Target", "Incoming")
    ]
    write_record(target, workspace)
    write_record(
        source,
        workspace,
        ["[[mywork/Project/记录-Target.md]]", "[[mywork/Project/记录-Missing.md]]"],
        "\n正文 [[记录-Incoming]] [链接](记录-Incoming.md) ![[图片.png]]\n",
    )
    write_record(incoming, workspace, ["[[mywork/Project/记录-Source.md]]"])
    document = AppContainer.build("test").document
    result = document.inspect("mywork/Project/记录-Source.md")
    assert result["relations"]["out_degree"] == 1
    assert result["relations"]["in_degree"] == 1
    assert [i["name"] for i in result["relations"]["outgoing"]] == ["Target"]
    assert [i["name"] for i in result["relations"]["incoming"]] == ["Incoming"]
    assert result["relations"]["unresolved"][0]["resolution"] == "missing"
    assert any(i["code"] == "related-docs-missing" for i in result["issues"])
    write_record(source, workspace, [], "[[记录-Target]]\n")
    assert document.inspect("mywork/Project/记录-Target.md")["relations"]["incoming"] == []


def test_deleted_target_keeps_missing_edge_and_restores_without_source_parse(
    workspace: Path, monkeypatch
) -> None:
    domain = write_project_domain(workspace)
    source, target = domain / "记录-Source.md", domain / "记录-Target.md"
    write_record(target, workspace)
    write_record(source, workspace, ["[[mywork/Project/记录-Target.md]]"])
    document = AppContainer.build("test").document
    index = document._index
    index.reconcile()
    original = source.read_bytes()
    target.unlink()
    index.reconcile()
    edge = index._repository.load_edges(source="mywork/Project/记录-Source.md")[0]
    assert edge.resolution == "missing"
    assert edge.target_path == "mywork/Project/记录-Target.md"
    parsed_sources = []
    record = index._builder.record

    def track(path, *args):
        parsed_sources.append(path)
        return record(path, *args)

    monkeypatch.setattr(index._builder, "record", track)
    write_record(target, workspace)
    index.reconcile()
    assert parsed_sources == [target]
    assert (
        index._repository.load_edges(source="mywork/Project/记录-Source.md")[0].resolution
        == "resolved"
    )
    assert source.read_bytes() == original
    source.unlink()
    index.reconcile()
    assert index._repository.load_edges() == []


def test_exact_paths_disambiguate_and_non_queryable_target_is_missing(workspace: Path) -> None:
    domain = write_project_domain(workspace)
    other = domain / "sub"
    other.mkdir()
    for directory in (domain, other):
        write_record(directory / "记录-Shared.md", workspace)
    source = domain / "记录-Source.md"
    write_record(source, workspace, ["[[mywork/Project/sub/记录-Shared.md]]"])
    document = AppContainer.build("test").document
    result = document.inspect("mywork/Project/记录-Source.md")
    assert result["relations"]["outgoing"][0]["target"] == "mywork/Project/sub/记录-Shared.md"
    target = other / "记录-Shared.md"
    target.write_text(target.read_text().replace("type: record", "type: moc"), encoding="utf-8")
    assert document.inspect("mywork/Project/记录-Source.md")["relations"]["unresolved"]
    assert all(i.type != "moc" for i in document.list().items)


def test_delta_matches_full_rebuild_and_metadata_only_changes_preserve_fields(
    workspace: Path, monkeypatch
) -> None:
    import os

    domain = write_project_domain(workspace)
    source, target = domain / "记录-Source.md", domain / "记录-Target.md"
    write_record(target, workspace)
    write_record(source, workspace, ["[[mywork/Project/记录-Target.md]]"])
    index = AppContainer.build("test").document._index
    index.reconcile()
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    changed = index.reconcile()
    assert not changed.full_rebuild
    assert index._repository.load_documents({"mywork/Project/记录-Source.md"})[0].name == "Source"
    write_record(source, workspace, [])
    index.reconcile()
    before = index._repository.load_edges()
    docs = [(i.path, i.name, i.content_hash) for i in index._repository.load_documents()]
    index.rebuild()
    assert before == index._repository.load_edges()
    assert docs == [(i.path, i.name, i.content_hash) for i in index._repository.load_documents()]
