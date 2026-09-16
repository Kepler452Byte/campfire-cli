from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke, resolution
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import ProjectRegistrationRequest
from campfire_cli.app.workspace.service.project_service import ProjectService
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import campfire_home

project_cli = typer.Typer(
    help="注册代码项目及其 Workspace 文档领域",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service() -> ProjectService:
    root = campfire_home()
    return ProjectService(root, SqliteWorkspaceRepository(root))


def request(
    project_id: str,
    workspace_id: str,
    name: str,
    document_domain_id: str,
    local_path: Path | None,
    git_remote_url: str | None,
    default_branch: str | None,
    status: str,
    document_domain_path: str | None = None,
) -> ProjectRegistrationRequest:
    return ProjectRegistrationRequest(
        project_id=project_id,
        workspace_id=workspace_id,
        name=name,
        document_domain_id=document_domain_id,
        document_domain_path=document_domain_path,
        local_path=local_path,
        git_remote_url=git_remote_url,
        default_branch=default_branch,
        status=status,
    )


@project_cli.command("adopt")
def adopt(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--id", help="稳定 Project id"),
    name: str = typer.Option(..., "--name", help="Project 显示名称"),
    domain_id: str = typer.Option(..., "--domain", help="已有项目根 Domain 的稳定 id"),
    local_path: Path | None = typer.Option(None, "--local-path"),
    git_remote_url: str | None = typer.Option(None, "--git-remote-url"),
    default_branch: str | None = typer.Option(None, "--default-branch"),
    status: str = typer.Option("active", "--status"),
) -> None:
    """把已有 Domain 绑定为 Project 文档中心。"""

    def operation():
        resolved = resolution(ctx)
        payload = request(
            project_id,
            resolved.workspace_id,
            name,
            domain_id,
            local_path,
            git_remote_url,
            default_branch,
            status,
        )
        return service().adopt(payload)

    emit(invoke(operation))


@project_cli.command("update")
def update(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--id", help="要更新的稳定 Project id"),
    name: str | None = typer.Option(None, "--name"),
    domain_id: str | None = typer.Option(
        None, "--domain", help="新的项目根 Domain id；不修改时省略"
    ),
    local_path: Path | None = typer.Option(None, "--local-path"),
    git_remote_url: str | None = typer.Option(None, "--git-remote-url"),
    default_branch: str | None = typer.Option(None, "--default-branch"),
    status: str | None = typer.Option(None, "--status"),
) -> None:
    """只更新显式给出的 Project 字段。"""

    def operation():
        resolved = resolution(ctx)
        target = service()
        current = target.show(project_id)
        if current.workspace_id != resolved.workspace_id:
            raise ConfigurationError(
                f"Project {project_id} 属于 Workspace {current.workspace_id}，"
                f"当前选择的是 {resolved.workspace_id}"
            )
        current_local_path = Path(current.local_path) if current.local_path else None
        payload = request(
            project_id,
            current.workspace_id,
            name if name is not None else current.name,
            domain_id or current.document_domain_id,
            local_path if local_path is not None else current_local_path,
            git_remote_url if git_remote_url is not None else current.git_remote_url,
            default_branch if default_branch is not None else current.default_branch,
            status if status is not None else current.status,
        )
        return target.update(payload)

    emit(invoke(operation))


@project_cli.command("create")
def create(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--id", help="稳定 Project id"),
    name: str = typer.Option(..., "--name", help="Project 显示名称"),
    path: str = typer.Option(..., "--path", help="待创建项目根 Domain 的 Workspace 相对路径"),
    local_path: Path | None = typer.Option(None, "--local-path"),
    git_remote_url: str | None = typer.Option(None, "--git-remote-url"),
    default_branch: str | None = typer.Option(None, "--default-branch"),
    status: str = typer.Option("active", "--status"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览并初始化新 Project 文档中心；追加 --confirm 后创建并注册。"""

    def operation():
        workspace_id = resolution(ctx).workspace_id
        payload = request(
            project_id,
            workspace_id,
            name,
            f"project-{project_id}",
            local_path,
            git_remote_url,
            default_branch,
            status,
            path,
        )
        return service().create(payload, confirm)

    emit(invoke(operation))


@project_cli.command("list")
def list_projects(ctx: typer.Context) -> None:
    """列出当前 Workspace 的已注册 Project。"""
    emit(invoke(lambda: service().list(resolution(ctx).workspace_id)))


@project_cli.command("show")
def show(project_id: str) -> None:
    """显示一个 Project 的注册元数据。"""
    emit(invoke(lambda: service().show(project_id)))


@project_cli.command("resolve")
def resolve(path: Path | None = typer.Option(None, "--path")) -> None:
    """按本地路径和 Git remote 解析已注册 Project，不修改注册数据。"""
    emit(invoke(lambda: service().resolve(path or safe_cwd())))


@project_cli.command("check")
def check(project_id: str) -> None:
    """检查 Project 的源码路径、Git 信息和文档领域是否仍然有效。"""
    emit(invoke(lambda: service().check(project_id)))


@project_cli.command("bind")
def bind(
    project_id: str = typer.Option(..., "--id"),
    local_path: Path = typer.Option(..., "--local-path"),
) -> None:
    """在当前设备上绑定 Project 源码路径，不把绝对路径写入 Manifest。"""
    emit(invoke(lambda: service().bind(project_id, local_path)))
