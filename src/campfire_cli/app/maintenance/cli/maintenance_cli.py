from __future__ import annotations

import json

import typer

HELP_SETTINGS = {"help_option_names": ["-h", "--help"]}

maintenance_cli = typer.Typer(help="后续增量文档维护", context_settings=HELP_SETTINGS)


def emit(result: object) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@maintenance_cli.command("check")
def check(
    ctx: typer.Context,
    scope: str | None = typer.Option(None, "--scope", help="只显示指定 Vault 相对路径下的问题"),
    code: str | None = typer.Option(None, "--code", help="只显示指定错误代码"),
    severity: str | None = typer.Option(None, "--severity", help="只显示指定严重级别"),
    summary: bool = typer.Option(False, "--summary", help="只输出统计，不展开问题列表"),
) -> None:
    """汇总 Workspace 结构与文档问题并刷新 SQLite 当前状态。"""
    emit(ctx.obj.maintenance.check(scope=scope, code=code, severity=severity, summary=summary))


@maintenance_cli.command("sync")
def sync(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run"),
    scope: str | None = typer.Option(None, "--scope", help="只同步指定领域或治理根目录"),
) -> None:
    """同步 MOC 等确定性派生内容。

    Workspace 选择是根参数，例如：
    campfire --workspace personal maintenance sync --scope "mywork/项目"
    """
    emit(ctx.obj.maintenance.sync(dry_run, scope))
