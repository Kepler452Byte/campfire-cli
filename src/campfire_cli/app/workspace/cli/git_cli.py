from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import resolution
from campfire_cli.app.workspace.service.git_sync_service import GitSyncService
from campfire_cli.common.cli_output import emit, invoke

git_cli = typer.Typer(help="按需同步 Vault Git 仓库，不同步 Project 源码仓库")


@git_cli.command("sync")
def sync(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="获取、提交、合并并推送整个 Vault"),
    expected_plan: str | None = typer.Option(
        None, "--expected-plan", help="可选预览摘要，变化时拒绝执行"
    ),
) -> None:
    """默认只预览；确认后同步 upstream。冲突停止，定时任务须主动配置。"""

    def execute():
        resolved = resolution(ctx)
        return GitSyncService(Path(resolved.workspace), Path(resolved.state_root)).sync(
            confirm=confirm, expected_plan=expected_plan
        )

    result = invoke(execute)
    emit(result)
    if result["status"] == "blocked":
        raise typer.Exit(1)
