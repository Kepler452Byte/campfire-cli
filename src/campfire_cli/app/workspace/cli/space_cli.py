from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke, resolution
from campfire_cli.app.workspace.service.structure_service import SpaceService
from campfire_cli.config.settings import campfire_home

space_cli = typer.Typer(
    help="管理 Workspace 顶级内容空间", context_settings={"help_option_names": ["-h", "--help"]}
)


def service(ctx: typer.Context) -> SpaceService:
    resolved = resolution(ctx)
    return SpaceService(Path(resolved.workspace), campfire_home())


@space_cli.command("list")
def list_spaces(ctx: typer.Context) -> None:
    emit(invoke(lambda: service(ctx).list()))


@space_cli.command("show")
def show(ctx: typer.Context, space_id: str) -> None:
    emit(invoke(lambda: service(ctx).show(space_id)))


@space_cli.command("check")
def check(
    ctx: typer.Context,
    space_id: str | None = typer.Option(None, "--space", help="只检查指定 Space id"),
) -> None:
    emit(invoke(lambda: service(ctx).check(space_id)))


@space_cli.command("create")
def create(
    ctx: typer.Context,
    space_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    path: str = typer.Option(..., "--path"),
    space_type: str = typer.Option(..., "--type"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(invoke(lambda: service(ctx).create(space_id, name, path, space_type, confirm)))


@space_cli.command("adopt")
def adopt(
    ctx: typer.Context,
    space_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    path: str = typer.Option(..., "--path"),
    space_type: str = typer.Option(..., "--type"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(invoke(lambda: service(ctx).adopt(space_id, name, path, space_type, confirm)))
