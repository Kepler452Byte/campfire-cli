from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from typer.testing import CliRunner

from campfire_cli.app.document.schema import DocumentApplyRequest
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry
from campfire_cli.app.workspace.service.structure_service import DomainService
from campfire_cli.common.database.models import WorkspaceDomain
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import AppError, ConfigurationError
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer
from campfire_cli.main import app


@pytest.fixture
def domain_tree(workspace: Path) -> AppContainer:
    service = DomainService(workspace, campfire_home())
    for domain_id, path in (
        ("finance", "mynote/金融"),
        ("child", "mynote/金融/子领域"),
        ("other", "mynote/其他"),
    ):
        service.create(
            domain_id=domain_id,
            name=domain_id,
            path=path,
            domain_type="knowledge-domain",
            governance="knowledge-base",
            confirm=True,
        )
    container = AppContainer.build("test")
    for path in ("mynote/金融/子领域/知识-说明.md", "mynote/其他/知识-引用.md"):
        values = {"description": "测试"}
        if "引用" in path:
            values["related_docs"] = '["[[mynote/金融/子领域/知识-说明.md]]"]'
        result = container.document.apply(
            DocumentApplyRequest(
                path=path,
                document_type="knowledge",
                values=values,
                confirm=True,
            )
        )
        assert result.status == "applied"
        with (workspace / result.target).open("a", encoding="utf-8") as handle:
            handle.write("\n未提交的人工正文 [[mynote/金融/子领域/知识-说明.md]]\n")
    (workspace / "mynote/金融/附件.bin").write_bytes(b"\x00\xffasset")
    assert container.maintenance.sync(scope="mynote").status == "synced"
    return container


def indexed_paths(container: AppContainer) -> dict[str, str]:
    session = container.maintenance._repository._session
    return {row.domain_id: row.path for row in session.scalars(select(WorkspaceDomain))}


@pytest.mark.parametrize("query_first", [False, True])
def test_external_rename_first_sync(
    workspace: Path, domain_tree: AppContainer, query_first: bool
) -> None:
    (workspace / "mynote/金融").rename(workspace / "mynote/金融新")
    if query_first:
        domain_tree.document.inspect("mynote/金融新/子领域/知识-说明.md")
    result = domain_tree.maintenance.sync(scope="mynote/金融新")
    assert result.status == "synced", result
    assert indexed_paths(domain_tree) == {
        "finance": "mynote/金融新",
        "child": "mynote/金融新/子领域",
        "other": "mynote/其他",
    }
    assert domain_tree.maintenance.sync(scope="mynote/金融新").generated_file_count == 0


def test_duplicate_identity_outside_scope_blocks(
    workspace: Path, domain_tree: AppContainer
) -> None:
    before = indexed_paths(domain_tree)
    shutil.copytree(workspace / "mynote/金融", workspace / "mynote/重复")
    result = domain_tree.maintenance.sync(scope="mynote/金融")
    assert result.status == "blocked"
    issue = next(item for item in result.issues if item.code == "duplicate-domain-id")
    assert "mynote/金融" in issue.detail and "mynote/重复" in issue.detail
    assert not result.write_performed
    assert indexed_paths(domain_tree) == before


def test_folder_rename_cli_preserves_content_and_identity(
    workspace: Path, domain_tree: AppContainer
) -> None:
    runner = CliRunner()
    args = [
        "--workspace",
        "test",
        "workspace",
        "domain",
        "rename",
        "--domain",
        "finance",
        "--folder-name",
        "金融新",
    ]
    source = workspace / "mynote/金融"
    original = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    plan = json.loads(preview.output)
    assert plan["path_changed"] and plan["old_path"] == "mynote/金融"
    assert plan["follow_up"] == [] and source.exists()
    result = runner.invoke(app, args + ["--expected-plan", plan["expected_plan"], "--confirm"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "applied", payload
    target = workspace / payload["path"]
    assert not source.exists()
    assert {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    } == original
    linked = parse_document((workspace / "mynote/其他/知识-引用.md").read_text(encoding="utf-8"))
    assert linked.frontmatter["related_docs"] == ["[[mynote/金融新/子领域/知识-说明.md]]"]
    assert "[[mynote/金融/子领域/知识-说明.md]]" in linked.body
    assert domain_tree.maintenance.sync(scope="mynote/金融新").status == "synced"
    assert indexed_paths(domain_tree)["child"] == "mynote/金融新/子领域"


def test_rename_plan_protects_assets_and_new_files(
    workspace: Path, domain_tree: AppContainer
) -> None:
    service = domain_tree.domain_restructure
    plan = service.rename("finance", folder_name="新领域")
    (workspace / "mynote/金融/新增.txt").write_text("new", encoding="utf-8")
    blocked = service.rename(
        "finance", folder_name="新领域", expected_plan=plan.expected_plan, confirm=True
    )
    assert blocked.status == "blocked" and blocked.issues[0]["code"] == "plan-changed"
    assert not blocked.write_performed and not blocked.follow_up
    assert (workspace / "mynote/金融").is_dir()


def test_selective_rename_and_conflicts(workspace: Path, domain_tree: AppContainer) -> None:
    service = domain_tree.domain_restructure
    display = service.rename("finance", "金融显示", confirm=True)
    assert display.path == "mynote/金融" and not display.path_changed
    with pytest.raises(ConfigurationError):
        service.rename("finance", folder_name="其他")
    for invalid in ("../outside", "a/b", "a\\b", "CON", "", ".", "bad."):
        with pytest.raises(ConfigurationError):
            service.rename("finance", folder_name=invalid)
    plan = service.rename("finance", "新显示", folder_name="新目录")
    result = service.rename(
        "finance", "新显示", folder_name="新目录", expected_plan=plan.expected_plan, confirm=True
    )
    assert result.status == "applied" and result.name == "新显示"
    assert result.domain_id == "finance" and result.path == "mynote/新目录"


def test_rename_write_failure_rolls_back(
    workspace: Path, domain_tree: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = domain_tree.domain_restructure
    original = (workspace / "mynote/其他/知识-引用.md").read_bytes()
    plan = service.rename("finance", folder_name="新目录")

    def fail(*args):
        raise PermissionError("file occupied")

    monkeypatch.setattr("campfire_cli.common.filesystem.change_set.atomic_write", fail)
    with pytest.raises(AppError) as exc:
        service.rename(
            "finance", folder_name="新目录", expected_plan=plan.expected_plan, confirm=True
        )
    assert exc.value.code == "domain-write-failed"
    assert (workspace / "mynote/金融").is_dir() and not (workspace / "mynote/新目录").exists()
    assert (workspace / "mynote/其他/知识-引用.md").read_bytes() == original


def test_sync_database_failure_rolls_back_and_retries(
    workspace: Path, domain_tree: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = domain_tree.maintenance
    before = indexed_paths(domain_tree)
    (workspace / "mynote/金融").rename(workspace / "mynote/金融新")
    marker = workspace / "mynote/金融新/_总览/MOC-finance总览.md"
    original = marker.read_bytes()
    session = service._repository._session
    commit = session.commit

    def fail():
        if any(isinstance(item, WorkspaceDomain) for item in session.new):
            raise OperationalError("insert", {}, Exception("locked"))
        commit()

    monkeypatch.setattr(session, "commit", fail)
    result = service.sync(scope="mynote/金融新")
    assert result.status == "blocked" and not result.write_performed
    assert result.issues[0].code == "domain-index-write-failed"
    assert marker.read_bytes() == original and indexed_paths(domain_tree) == before
    monkeypatch.setattr(session, "commit", commit)
    assert service.sync(scope="mynote/金融新").status == "synced"


def test_case_only_rename_is_explicit(workspace: Path, domain_tree: AppContainer) -> None:
    service = DomainService(workspace, campfire_home())
    service.create(
        domain_id="case",
        name="Case",
        path="mynote/Case",
        domain_type="knowledge-domain",
        governance="knowledge-base",
        confirm=True,
    )
    if (workspace / "mynote/case").exists():
        with pytest.raises(ConfigurationError) as exc:
            domain_tree.domain_restructure.rename("case", folder_name="case")
        assert exc.value.code == "case-only-rename-unsupported"
        assert (workspace / "mynote/Case").is_dir()
    else:
        plan = domain_tree.domain_restructure.rename("case", folder_name="case")
        result = domain_tree.domain_restructure.rename(
            "case", folder_name="case", expected_plan=plan.expected_plan, confirm=True
        )
        assert result.status == "applied" and (workspace / "mynote/case").is_dir()


def test_new_domain_during_sync_blocks(
    workspace: Path, domain_tree: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = domain_tree.maintenance._document_index
    original = index.relation_views

    def change(sources):
        result = original(sources)
        shutil.copytree(workspace / "mynote/金融", workspace / "mynote/重复")
        return result

    monkeypatch.setattr(index, "relation_views", change)
    result = domain_tree.maintenance.sync(scope="mynote/金融")
    assert result.status == "blocked" and result.issues[0].code == "concurrent-change"
    assert not result.write_performed


def test_project_binding_survives_folder_rename(workspace: Path) -> None:
    service = DomainService(workspace, campfire_home())
    service.create(
        domain_id="project-root",
        name="Project",
        path="mywork/Project",
        domain_type="project-domain",
        governance="project-docs",
        confirm=True,
    )
    manifest = workspace / ".campfire.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "projects: []",
            "projects:\n- id: example\n  name: Example\n"
            "  document_domain_id: project-root\n  status: active",
        ),
        encoding="utf-8",
    )
    repository = SqliteWorkspaceRepository(campfire_home())
    repository.save_project(
        ProjectEntry(
            id="example", workspace_id="test", name="Example", document_domain_id="project-root"
        )
    )
    original = manifest.read_bytes()
    container = AppContainer.build("test")
    plan = container.domain_restructure.rename("project-root", folder_name="新项目")
    result = container.domain_restructure.rename(
        "project-root", folder_name="新项目", expected_plan=plan.expected_plan, confirm=True
    )
    assert result.status == "applied" and not result.affected_projects
    assert manifest.read_bytes() == original
    assert repository.list_projects("test")[0].document_domain_id == "project-root"
    assert container.maintenance.sync(scope="mywork/新项目").status == "synced"


def test_postcheck_failure_reports_written_files(
    workspace: Path, domain_tree: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = domain_tree.domain_restructure
    plan = service.rename("finance", folder_name="新目录")

    def fail():
        raise ConfigurationError("postcheck unavailable")

    monkeypatch.setattr(service._domains, "check", fail)
    result = service.rename(
        "finance", folder_name="新目录", expected_plan=plan.expected_plan, confirm=True
    )
    assert result.status == "needs-review" and result.write_performed
    assert result.issues[0]["code"] == "domain-postcheck-failed"
    assert (workspace / "mynote/新目录").is_dir()
