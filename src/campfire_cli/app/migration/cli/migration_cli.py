from __future__ import annotations

import json
from pathlib import Path

import typer

from campfire_cli.common.governance import enrich_issue

migration_cli = typer.Typer(
    help="一次性存量批量治理",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def emit(result: object) -> None:
    payload = result.model_dump(mode="json")
    payload["issues"] = [enrich_issue(issue) for issue in payload.get("issues", [])]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@migration_cli.command("inventory")
def inventory(
    ctx: typer.Context,
    scope: str = typer.Option(..., "--scope"),
    batch: str = typer.Option(..., "--batch"),
) -> None:
    """冻结范围并生成批次事实清单。"""
    emit(ctx.obj.migration.inventory(batch, scope))


@migration_cli.command("plan")
def plan(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    spec: Path | None = typer.Option(
        None, "--spec", help="显式迁移意图 YAML/JSON；支持跨目录移动和 Frontmatter Patch"
    ),
) -> None:
    """生成带源哈希且默认未审批的逐文件计划。"""
    emit(ctx.obj.migration.plan(batch, spec))


@migration_cli.command("apply")
def apply(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预检或执行已审批批次。"""
    emit(ctx.obj.migration.apply(batch, confirm))


@migration_cli.command("verify")
def verify(ctx: typer.Context, batch: str = typer.Option(..., "--batch")) -> None:
    """执行批次最终验收并固化结果。"""
    emit(ctx.obj.migration.verify(batch))
