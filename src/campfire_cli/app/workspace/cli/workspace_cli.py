from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import (
    ProjectRegistrationRequest,
    WorkspaceCreateRequest,
    WorkspaceCreateResult,
)
from campfire_cli.app.workspace.service.project_service import ProjectService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer

workspace_cli = typer.Typer(
    help="注册、初始化和解析多个 Workspace",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service() -> WorkspaceService:
    root = campfire_home()
    return WorkspaceService(root, SqliteWorkspaceRepository(root))


def selector(ctx: typer.Context) -> str | None:
    return ctx.find_root().params.get("workspace")


def resolution(ctx: typer.Context):
    return service().resolve(selector(ctx), safe_cwd())


@workspace_cli.command("create")
def create(
    workspace_id: str = typer.Option(..., "--id"),
    path: Path = typer.Option(..., "--path"),
    make_default: bool = typer.Option(False, "--default"),
    demo: str | None = typer.Option(None, "--demo", help="可选演示项目：hello-world"),
) -> None:
    """从零创建 Workspace 基础目录，并注册和初始化治理能力。"""
    request = WorkspaceCreateRequest(
        workspace_id=workspace_id, path=path, make_default=make_default
    )
    demo_request = invoke(lambda: _demo_request(demo, workspace_id))
    created = invoke(lambda: service().create(request))
    setup = invoke(lambda: AppContainer.setup(Path(created.workspace), make_default, workspace_id))
    demo_result = (
        invoke(
            lambda: ProjectService(
                campfire_home(), SqliteWorkspaceRepository(campfire_home())
            ).create(demo_request, confirm=True)
        )
        if demo_request
        else None
    )
    emit(
        WorkspaceCreateResult(
            **created.model_dump(),
            manifest=setup["manifest"],
            resources=setup["resources"],
            health=setup["health"],
            demo=(
                {
                    "id": demo,
                    "project": demo_result.project.model_dump(mode="json"),
                    "document_domain_path": demo_result.document_domain_path,
                }
                if demo_result
                else None
            ),
        )
    )


def _demo_request(demo: str | None, workspace_id: str) -> ProjectRegistrationRequest | None:
    if demo is None:
        return None
    if demo != "hello-world":
        raise ConfigurationError("--demo 仅支持：hello-world")
    return ProjectRegistrationRequest(
        project_id="hello-world",
        workspace_id=workspace_id,
        name="Hello World",
        document_domain_id="project-hello-world",
        document_domain_path="mywork/【Hello World】文档中心",
        git_remote_url="https://github.com/octocat/Hello-World.git",
        default_branch="master",
    )


@workspace_cli.command("list")
def list_workspaces() -> None:
    """列出所有注册的 Workspace。"""
    emit(invoke(service().list))


@workspace_cli.command("show")
def show(workspace_id: str) -> None:
    """显示一个 Workspace 的路径和本机状态目录。"""
    emit(invoke(lambda: service().show(workspace_id)))


@workspace_cli.command("resolve")
def resolve(ctx: typer.Context) -> None:
    """按显式选择、当前目录或默认值解析 Workspace。"""
    emit(invoke(lambda: resolution(ctx)))


@workspace_cli.command("set-default")
def set_default(workspace_id: str) -> None:
    """设置默认 Workspace。"""
    emit(invoke(lambda: service().set_default(workspace_id)))


@workspace_cli.command("rebuild")
def rebuild(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """从 Manifest 和 Markdown SSOT 重建本机派生索引。"""
    if not confirm:
        emit(
            {
                "status": "ready",
                "operation": "replace-workspace-derived-indexes",
                "write_performed": False,
            }
        )
        return
    from campfire_cli.container import AppContainer

    emit(invoke(lambda: AppContainer.build(selector(ctx)).maintenance.check(summary=True)))


@workspace_cli.command("export")
def export_registry(output: Path = typer.Option(..., "--output")) -> None:
    """将 Workspace 与 Project 注册数据导出为 JSON 备份。"""
    emit(invoke(lambda: service().export_registry(output)))


@workspace_cli.command("import")
def import_registry(
    input_path: Path = typer.Option(..., "--input"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """校验注册数据备份；追加 --confirm 后替换当前注册数据。"""
    emit(invoke(lambda: service().import_registry(input_path, confirm)))
