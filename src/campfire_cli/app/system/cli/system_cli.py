from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.package_version import installed_version
from campfire_cli.container import AppContainer


def version_result() -> dict:
    return {"status": "ok", "version": installed_version(), "package": "campfire-cli"}


def version_option(value: bool) -> None:
    if value:
        emit(version_result())
        raise typer.Exit()


def emit_system(result: dict) -> None:
    blocked = result.get("status") == "blocked"
    emit(result, err=blocked)
    if blocked:
        raise typer.Exit(3)


def register_system_commands(app: typer.Typer) -> None:
    @app.command("version")
    def version() -> None:
        """显示安装包版本，不初始化本机状态。"""
        emit(version_result())

    @app.command("tree")
    def tree(ctx: typer.Context) -> None:
        """从实际命令定义生成完整 CLI 命令树。"""
        from campfire_cli.common.cli_output import command_tree

        emit({"status": "ok", "tree": command_tree(ctx.find_root().command, "campfire")})

    @app.command("setup")
    def setup(
        path: Path | None = typer.Option(
            None, "--path", help="Workspace 根目录；缺省仅对齐全局资源"
        ),
        workspace_id: str | None = typer.Option(
            None, "--id", help="缺少 .campfire.yaml 时的稳定 id"
        ),
        verbose: bool = typer.Option(False, "--verbose", help="输出逐文件资源操作与哈希"),
        make_default: bool = typer.Option(False, "--default", help="设为默认 Workspace"),
    ) -> None:
        """初始化本机资源并接入 Workspace，不开启定时任务。"""

        def operation() -> dict:
            if path is None and workspace_id is not None:
                raise ConfigurationError("--id 只能与 --path 一起使用", code="invalid-option")
            service = AppContainer.build_system()
            return (
                service.setup_global_resources(verbose)
                if path is None
                else service.setup(path, make_default, workspace_id, verbose)
            )

        emit_system(invoke(operation))

    @app.command("upgrade")
    def upgrade(
        skip_package: bool = typer.Option(
            False, "--skip-package", help="离线对齐资源，不查询或更新包"
        ),
    ) -> None:
        """更新包并对齐资源；后台启动不等于升级完成。"""
        emit_system(invoke(lambda: AppContainer.build_upgrade().upgrade(skip_package)))

    agent = typer.Typer(
        help="查询本机 Agent 资源升级结果", context_settings={"help_option_names": ["-h", "--help"]}
    )

    @agent.command("upgrade-status")
    def upgrade_status(operation_id: str) -> None:
        """查询一次升级的包、资源阶段与 Workspace 结果。"""
        emit_system(invoke(lambda: AppContainer.build_upgrade().status(operation_id)))

    app.add_typer(agent, name="agent")
