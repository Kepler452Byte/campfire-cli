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
from campfire_cli.common.filesystem.cwd import safe_cwd

type_cli = typer.Typer(
    help="查看文档类型与文件名前缀契约",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service(ctx: typer.Context) -> DocumentTypeService:
    selector = ctx.find_root().params.get("workspace")
    root = campfire_home()
    resolution = WorkspaceService(root, SqliteWorkspaceRepository(root)).resolve(
        selector, safe_cwd()
    )
    settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
    return DocumentTypeService(
        settings.workspace_id,
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
