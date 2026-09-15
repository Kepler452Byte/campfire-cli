from __future__ import annotations

import json
from pathlib import Path

import typer

from campfire_cli.common.governance import enrich_issue
from campfire_cli.container import AppContainer

restructure_cli = typer.Typer(
    help="按审批计划重构 Workspace 物理结构",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def emit(result: object) -> None:
    payload = result.model_dump(mode="json")
    payload["issues"] = [enrich_issue(issue) for issue in payload.get("issues", [])]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def service(ctx: typer.Context, workspace: str | None):
    selector = workspace or ctx.find_root().params.get("workspace")
    return AppContainer.build(selector).restructure


@restructure_cli.command("inventory")
def inventory(
    ctx: typer.Context,
    scope: str = typer.Option(..., "--scope"),
    batch: str = typer.Option(..., "--batch"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """冻结范围并生成批次事实清单。"""
    emit(service(ctx, workspace).inventory(batch, scope))


@restructure_cli.command("plan")
def plan(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    spec: Path | None = typer.Option(
        None, "--spec", help="显式重构意图 YAML/JSON；支持跨目录移动和 Frontmatter Patch"
    ),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """生成带源哈希且默认未审批的逐文件计划。"""
    emit(service(ctx, workspace).plan(batch, spec))


@restructure_cli.command("apply")
def apply(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """预检或执行已审批批次。"""
    emit(service(ctx, workspace).apply(batch, confirm))


@restructure_cli.command("verify")
def verify(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """执行批次最终验收并固化结果。"""
    emit(service(ctx, workspace).verify(batch))
