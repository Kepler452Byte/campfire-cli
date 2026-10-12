from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli import __version__
from campfire_cli.common.cli_output import command_tree, emit, invoke
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.container import AppContainer


def register_system_commands(app: typer.Typer) -> None:
    @app.command("version")
    def version() -> None:
        """显示 CLI 版本。"""
        emit({"status": "ok", "version": __version__})

    @app.command("tree")
    def tree(ctx: typer.Context) -> None:
        """显示完整 CLI 命令树，便于人类和 Agent 渐进式发现能力。"""
        emit({"status": "ok", "tree": command_tree(ctx.find_root().command, "campfire")})

    @app.command("setup")
    def setup(
        path: Path | None = typer.Option(
            None, "--path", help="要初始化的 Workspace 根目录；缺省时仅同步全局资源并输出接入引导"
        ),
        workspace_id: str | None = typer.Option(
            None, "--id", help="缺少 .campfire.yaml 时使用的稳定 Workspace id"
        ),
        verbose: bool = typer.Option(
            False, "--verbose", help="输出逐文件资源路径与哈希；默认仅输出摘要"
        ),
        make_default: bool = typer.Option(False, "--default", help="设为默认 Workspace"),
    ) -> None:
        """从 .campfire.yaml 配置本机，或为已注册 Workspace 创建首份 Manifest。"""

        def operation() -> dict[str, object]:
            if path is None and workspace_id is not None:
                raise ConfigurationError("--id 只能与 --path 一起使用", code="invalid-option")
            result = (
                AppContainer.build_system().setup_global_resources()
                if path is None
                else AppContainer.build_system().setup(path, make_default, workspace_id)
            )
            if not verbose:
                resources = result.get("resources", {})
                result["resources"] = {
                    key: (
                        {
                            **{
                                field: value
                                for field, value in item.items()
                                if field != "operations"
                            },
                            "operation_count": len(item.get("operations", [])),
                        }
                        if isinstance(item, dict)
                        else item
                    )
                    for key, item in resources.items()
                }
                result["details_hint"] = (
                    "Repeat setup with --verbose to obtain resource operations and hashes."
                )
            return result

        emit(invoke(operation))

    @app.command("upgrade")
    def upgrade(
        skip_package: bool = typer.Option(
            False, "--skip-package", hidden=True, help="内部参数：跳过包自更新，仅对齐治理资源"
        ),
    ) -> None:
        """一条幂等命令升级 campfire：更新包并对齐治理资源（Skill、Base、提示词、Schema）。"""
        emit(invoke(lambda: AppContainer.build_system().upgrade(skip_package=skip_package)))
