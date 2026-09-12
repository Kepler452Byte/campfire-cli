from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from campfire_cli.app.document.repository.document_type_repository import (
    DocumentTypeRepository,
)
from campfire_cli.app.document.service.document_type_service import DocumentTypeService
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.exceptions import AppError
from campfire_cli.config.settings import WorkspaceSettings, campfire_home

type_cli = typer.Typer(
    help="查看和同步文档类型与文件名前缀契约",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service(ctx: typer.Context) -> DocumentTypeService:
    selector = ctx.find_root().params.get("workspace")
    root = campfire_home()
    resolution = WorkspaceService(root, SqliteWorkspaceRepository(root)).resolve(
        selector, Path.cwd()
    )
    settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
    return DocumentTypeService(
        settings.workspace_id,
        settings.state_root,
        DocumentTypeRepository(settings.state_root),
    )


def invoke(operation: Callable[[], dict[str, Any]]) -> None:
    try:
        typer.echo(json.dumps(operation(), ensure_ascii=False, indent=2))
    except AppError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(exc.exit_code) from exc


@type_cli.command("list")
def list_types(ctx: typer.Context) -> None:
    """列出当前 Workspace 的单选文档类型和文件名前缀。"""
    invoke(lambda: service(ctx).list_types())


@type_cli.command("sync")
def sync(ctx: typer.Context, confirm: bool = typer.Option(False, "--confirm")) -> None:
    """预览默认类型契约；追加 --confirm 后更新当前 Workspace。"""
    invoke(lambda: service(ctx).sync(confirm))
