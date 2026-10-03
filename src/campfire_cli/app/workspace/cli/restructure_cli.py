from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.common.cli_output import emit as emit_json
from campfire_cli.common.cli_output import invoke
from campfire_cli.common.governance import enrich_issue
from campfire_cli.container import AppContainer

restructure_cli = typer.Typer(
    help="按审批计划重构 Workspace 物理结构",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def emit(result: object) -> None:
    payload = result.model_dump(mode="json")
    payload["issues"] = [enrich_issue(issue) for issue in payload.get("issues", [])]
    emit_json(payload)


def service(ctx: typer.Context):
    return AppContainer.build(ctx.find_root().params.get("workspace")).restructure


@restructure_cli.command("inventory")
def inventory(
    ctx: typer.Context,
    scope: str = typer.Option(..., "--scope"),
    batch: str = typer.Option(..., "--batch"),
) -> None:
    """冻结范围并生成批次事实清单。"""
    emit(invoke(lambda: service(ctx).inventory(batch, scope)))


@restructure_cli.command("plan")
def plan(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    spec: Path | None = typer.Option(
        None,
        "--spec",
        help="YAML/JSON 意图规格文件",
    ),
) -> None:
    """生成带源哈希且默认未审批的逐文件计划。

    无 --spec：只规范化类型与文件名。
    移动或 Frontmatter Patch：使用 operations spec。
    完整格式见 Restructure Skill reference。
    """
    emit(invoke(lambda: service(ctx).plan(batch, spec)))


@restructure_cli.command("apply")
def apply(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预检或执行已审批批次。"""
    emit(invoke(lambda: service(ctx).apply(batch, confirm)))


@restructure_cli.command("verify")
def verify(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
) -> None:
    """执行批次最终验收并固化结果。"""
    emit(invoke(lambda: service(ctx).verify(batch)))
