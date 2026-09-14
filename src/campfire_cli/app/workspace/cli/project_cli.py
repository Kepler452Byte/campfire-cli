from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import ProjectUpsertRequest
from campfire_cli.app.workspace.service.project_service import ProjectService
from campfire_cli.config.settings import campfire_home
from campfire_cli.common.filesystem.cwd import safe_cwd

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
    document_domain: str,
    local_path: Path | None,
    git_remote_url: str | None,
    default_branch: str | None,
    status: str,
) -> ProjectUpsertRequest:
    return ProjectUpsertRequest(
        project_id=project_id,
        workspace_id=workspace_id,
        name=name,
        document_domain=document_domain,
        local_path=local_path,
        git_remote_url=git_remote_url,
        default_branch=default_branch,
        status=status,
    )


def project_options(operation: str):
    def command(
        project_id: str = typer.Option(..., "--id"),
        workspace_id: str = typer.Option(..., "--workspace"),
        name: str = typer.Option(..., "--name"),
        document_domain: str = typer.Option(..., "--document-domain"),
        local_path: Path | None = typer.Option(None, "--local-path"),
        git_remote_url: str | None = typer.Option(None, "--git-remote-url"),
        default_branch: str | None = typer.Option(None, "--default-branch"),
        status: str = typer.Option("active", "--status"),
    ) -> None:
        payload = request(
            project_id,
            workspace_id,
            name,
            document_domain,
            local_path,
            git_remote_url,
            default_branch,
            status,
        )
        target = service()
        emit(invoke(lambda: getattr(target, operation)(payload)))

    return command


project_cli.command("add", help="注册一个新 Project；提供本地 Git 路径时自动发现 remote 和分支。")(
    project_options("add")
)
project_cli.command("update", help="完整更新一个已注册 Project。")(project_options("update"))


@project_cli.command("create")
def create(
    project_id: str = typer.Option(..., "--id"),
    workspace_id: str = typer.Option(..., "--workspace"),
    name: str = typer.Option(..., "--name"),
    document_domain: str = typer.Option(..., "--document-domain"),
    local_path: Path | None = typer.Option(None, "--local-path"),
    git_remote_url: str | None = typer.Option(None, "--git-remote-url"),
    default_branch: str | None = typer.Option(None, "--default-branch"),
    status: str = typer.Option("active", "--status"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览并初始化新 Project 文档中心；追加 --confirm 后创建并注册。"""
    payload = request(
        project_id,
        workspace_id,
        name,
        document_domain,
        local_path,
        git_remote_url,
        default_branch,
        status,
    )
    emit(invoke(lambda: service().create(payload, confirm)))


@project_cli.command("list")
def list_projects(workspace_id: str | None = typer.Option(None, "--workspace")) -> None:
    """列出全部 Project，或按 Workspace 过滤。"""
    emit(invoke(lambda: service().list(workspace_id)))


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
