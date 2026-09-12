from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.structure_service import SpaceService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.config.settings import campfire_home

space_cli = typer.Typer(
    help="管理 Workspace 顶级内容空间", context_settings={"help_option_names": ["-h", "--help"]}
)


def service(workspace: str | None) -> SpaceService:
    home = campfire_home()
    resolved = WorkspaceService(home, SqliteWorkspaceRepository(home)).resolve(
        workspace, Path.cwd()
    )
    return SpaceService(Path(resolved.workspace), home)


@space_cli.command("list")
def list_spaces(workspace: str | None = typer.Option(None, "--workspace")) -> None:
    emit(invoke(lambda: service(workspace).list()))


@space_cli.command("show")
def show(space_id: str, workspace: str | None = typer.Option(None, "--workspace")) -> None:
    emit(invoke(lambda: service(workspace).show(space_id)))


@space_cli.command("check")
def check(workspace: str | None = typer.Option(None, "--workspace")) -> None:
    emit(invoke(lambda: service(workspace).check()))


@space_cli.command("create")
def create(
    space_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    path: str = typer.Option(..., "--path"),
    space_type: str = typer.Option(..., "--type"),
    workspace: str | None = typer.Option(None, "--workspace"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(invoke(lambda: service(workspace).create(space_id, name, path, space_type, confirm)))


@space_cli.command("adopt")
def adopt(
    space_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    path: str = typer.Option(..., "--path"),
    space_type: str = typer.Option(..., "--type"),
    workspace: str | None = typer.Option(None, "--workspace"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(invoke(lambda: service(workspace).adopt(space_id, name, path, space_type, confirm)))
