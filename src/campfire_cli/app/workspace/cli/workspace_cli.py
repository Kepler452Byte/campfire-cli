from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import typer
from pydantic import BaseModel

from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceCreateRequest
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.exceptions import AppError
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import campfire_home

workspace_cli = typer.Typer(
    help="注册、初始化和解析多个 Workspace",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service() -> WorkspaceService:
    root = campfire_home()
    return WorkspaceService(root, SqliteWorkspaceRepository(root))


def emit(result: BaseModel) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


def invoke[ResultT: BaseModel](operation: Callable[[], ResultT]) -> ResultT:
    try:
        return operation()
    except AppError as exc:
        typer.echo(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), err=True
        )
        raise typer.Exit(exc.exit_code) from exc


def initialize(workspace_id: str, path: Path, make_default: bool) -> BaseModel:
    return invoke(
        lambda: service().add(
            WorkspaceCreateRequest(workspace_id=workspace_id, path=path, make_default=make_default)
        )
    )


def setup_workspace(path: Path, make_default: bool) -> BaseModel:
    return invoke(lambda: service().setup(path, make_default))


@workspace_cli.command("add", hidden=True)
def add(
    workspace_id: str = typer.Option(..., "--id"),
    path: Path = typer.Option(..., "--path"),
    make_default: bool = typer.Option(False, "--default"),
) -> None:
    """注册并初始化一个已存在的 Workspace。"""
    emit(initialize(workspace_id, path, make_default))


@workspace_cli.command("attach", hidden=True)
def attach(
    path: Path = typer.Option(..., "--path"),
    make_default: bool = typer.Option(False, "--default"),
) -> None:
    """根据 Vault 根目录的 .campfire.yaml 接入本机。"""
    emit(setup_workspace(path, make_default))


@workspace_cli.command("create")
def create(
    workspace_id: str = typer.Option(..., "--id"),
    path: Path = typer.Option(..., "--path"),
    make_default: bool = typer.Option(False, "--default"),
) -> None:
    """从零创建 Workspace 基础目录，并注册和初始化治理能力。"""
    request = WorkspaceCreateRequest(
        workspace_id=workspace_id, path=path, make_default=make_default
    )
    emit(invoke(lambda: service().create(request)))


@workspace_cli.command("list")
def list_workspaces() -> None:
    """列出所有注册的 Workspace。"""
    emit(invoke(service().list))


@workspace_cli.command("show")
def show(workspace_id: str) -> None:
    """显示一个 Workspace 的路径和本机状态目录。"""
    emit(invoke(lambda: service().show(workspace_id)))


@workspace_cli.command("resolve")
def resolve(selector: str | None = typer.Option(None, "--workspace")) -> None:
    """按显式选择、当前目录或默认值解析 Workspace。"""
    emit(invoke(lambda: service().resolve(selector, safe_cwd())))


@workspace_cli.command("set-default")
def set_default(workspace_id: str) -> None:
    """设置默认 Workspace。"""
    emit(invoke(lambda: service().set_default(workspace_id)))


@workspace_cli.command("rebuild")
def rebuild(
    workspace: str | None = typer.Option(None, "--workspace"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """从 Manifest 和 Markdown SSOT 重建本机派生索引。"""
    if not confirm:
        typer.echo(
            json.dumps(
                {
                    "status": "ready",
                    "operation": "replace-workspace-derived-indexes",
                    "write_performed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    from campfire_cli.container import AppContainer

    emit(invoke(lambda: AppContainer.build(workspace).maintenance.check(summary=True)))


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
