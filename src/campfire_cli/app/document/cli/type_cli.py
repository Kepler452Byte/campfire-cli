from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.document.repository.document_type_repository import (
    DocumentTypeRepository,
)
from campfire_cli.app.document.service.rules.document_type_service import DocumentTypeService
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import WorkspaceSettings, campfire_home

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


@type_cli.command("list")
def list_types(ctx: typer.Context) -> None:
    """列出当前 Workspace 的单选文档类型和文件名前缀。"""
    emit(invoke(lambda: service(ctx).list_types()))
