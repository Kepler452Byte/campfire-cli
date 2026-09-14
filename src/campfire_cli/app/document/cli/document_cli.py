from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
import yaml

from campfire_cli.app.document.cli.profile_cli import profile_cli
from campfire_cli.app.document.cli.type_cli import type_cli
from campfire_cli.app.document.service.document_service import DocumentService
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.exceptions import AppError
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import WorkspaceSettings, campfire_home

document_cli = typer.Typer(
    help="创建、检查和维护文档及其规则",
    context_settings={"help_option_names": ["-h", "--help"]},
)
document_cli.add_typer(profile_cli, name="profile")
document_cli.add_typer(type_cli, name="type")


def service(ctx: typer.Context) -> DocumentService:
    selector = ctx.find_root().params.get("workspace")
    root = campfire_home()
    resolution = WorkspaceService(root, SqliteWorkspaceRepository(root)).resolve(
        selector, safe_cwd()
    )
    settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
    return DocumentService(settings)


def invoke(operation: Callable[[], dict[str, Any]]) -> None:
    try:
        typer.echo(json.dumps(operation(), ensure_ascii=False, indent=2))
    except AppError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(exc.exit_code) from exc


@document_cli.command("check")
def check(ctx: typer.Context, path: str = typer.Option(..., "--path")) -> None:
    """检查一篇 Markdown 文档是否符合当前类型与 Profile 契约。"""
    invoke(lambda: service(ctx).check(path))


@document_cli.command("kanban-check")
def kanban_check(ctx: typer.Context, path: str = typer.Option(..., "--path")) -> None:
    """检查文档是否满足 Obsidian Kanban 插件的渲染契约。"""
    invoke(lambda: service(ctx).kanban_check(path))


@document_cli.command("inspect")
def inspect(ctx: typer.Context, path: str = typer.Option(..., "--path")) -> None:
    """返回 Agent 治理单篇文档所需的类型、Profile、领域和问题上下文。"""
    invoke(lambda: service(ctx).inspect(path))


@document_cli.command("format")
def format_document(
    ctx: typer.Context,
    path: str = typer.Option(..., "--path"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览或执行一篇文档的 Frontmatter 字段排序。"""
    invoke(lambda: service(ctx).format(path, confirm))


def parse_values(items: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"--set 必须使用 field=value：{item}")
        key, raw = item.split("=", 1)
        if not key.strip():
            raise typer.BadParameter("--set 字段名不能为空")
        key = key.strip()
        if key in values:
            raise typer.BadParameter(f"--set 字段重复：{key}")
        values[key] = yaml.safe_load(raw)
    return values


@document_cli.command("upsert")
def upsert_document(
    ctx: typer.Context,
    path: str = typer.Option(..., "--path"),
    document_type: str | None = typer.Option(None, "--type"),
    set_values: list[str] | None = typer.Option(None, "--set"),
    body_file: Path | None = typer.Option(None, "--body-file"),
    append_section: str | None = typer.Option(None, "--append-section"),
    replace_body: bool = typer.Option(False, "--replace-body"),
    expected_hash: str | None = typer.Option(None, "--expected-hash"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """按 Profile 契约创建或安全更新一篇文档。"""
    from campfire_cli.container import AppContainer

    body = body_file.read_text(encoding="utf-8") if body_file else None
    container = AppContainer.build(ctx.find_root().params.get("workspace"))
    invoke(
        lambda: container.upsert_document(
            path,
            document_type=document_type,
            values=parse_values(set_values or []),
            body=body,
            append_section=append_section,
            replace_body=replace_body,
            expected_hash=expected_hash,
            confirm=confirm,
        )
    )
