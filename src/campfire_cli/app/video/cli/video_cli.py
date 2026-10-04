from collections.abc import Callable
from pathlib import Path

import typer

from campfire_cli.common.cli_output import JsonTyperGroup, emit
from campfire_cli.common.cli_output import invoke as invoke_app
from campfire_cli.common.exceptions import InputError
from campfire_cli.container import AppContainer

video_cli = typer.Typer(help="本地视频素材与保真图文交付，不解析 URL", cls=JsonTyperGroup)


def invoke(operation: Callable[[], dict]) -> dict:
    def guarded() -> dict:
        try:
            return operation()
        except (OSError, UnicodeError) as exc:
            raise InputError(
                "视频文件操作失败，请检查路径、权限和 UTF-8 编码",
                code="video-io-error",
                field="path",
                expected_type="accessible local path",
                detail=str(exc),
            ) from exc

    return invoke_app(guarded)


@video_cli.command("setup")
def setup(
    expected_plan: str | None = typer.Option(None, help="初始化预览返回的计划摘要"),
    confirm: bool = typer.Option(False, help="确认安装缺失视频依赖、下载默认模型并验证加载"),
) -> None:
    """一次启用视频能力；已有依赖和模型直接复用，不要求 Workspace。"""
    emit(
        invoke(
            lambda: AppContainer.build_video().setup(
                confirm=confirm,
                expected_plan=expected_plan,
            )
        )
    )


@video_cli.command("prepare")
def prepare(
    source: Path = typer.Option(..., help="只读本地视频路径，不接受 URL"),
    output: Path = typer.Option(..., help="Workspace 外尚不存在的素材目录"),
    model: Path | None = typer.Option(
        None,
        help="本地模型目录；默认使用 video setup 准备的模型，缺失时提示初始化",
    ),
    transcript: Path | None = typer.Option(
        None, help='UTF-8 JSON 数组，如 [{"start":0,"end":1,"text":"文字"}]；秒为单位'
    ),
    expected_plan: str | None = typer.Option(None, help="预览返回的计划摘要"),
    confirm: bool = typer.Option(False, help="按预览计划处理视频，不安装依赖或下载模型"),
) -> None:
    emit(
        invoke(
            lambda: AppContainer.build_video().prepare(
                source,
                output,
                model=model,
                transcript=transcript,
                expected_plan=expected_plan,
                confirm=confirm,
            )
        )
    )


@video_cli.command("inspect")
def inspect(
    bundle: Path = typer.Option(..., help="包含 material.json 的素材目录"),
    draft: Path | None = typer.Option(None, help="可选草稿 JSON；校验覆盖与图片引用"),
) -> None:
    emit(invoke(lambda: AppContainer.build_video().inspect(bundle, draft)))


@video_cli.command("frames")
def frames(
    source: Path = typer.Option(..., help="原始本地视频，须与素材哈希一致"),
    bundle: Path = typer.Option(..., help="已有素材目录"),
    at: list[float] = typer.Option(..., help="补帧秒数，可重复 --at"),
    expected_plan: str | None = typer.Option(None, help="预览返回的计划摘要"),
    confirm: bool = typer.Option(False, help="按预览计划补帧"),
) -> None:
    emit(
        invoke(
            lambda: AppContainer.build_video().frames(
                source,
                bundle,
                at,
                confirm=confirm,
                expected_plan=expected_plan,
            )
        )
    )


@video_cli.command("deliver")
def deliver(
    ctx: typer.Context,
    bundle: Path = typer.Option(..., help="素材目录"),
    draft: Path = typer.Option(..., help="经 Agent 整理的草稿 JSON，格式见内置视频 Skill"),
    path: str = typer.Option(..., help="Workspace 内已有的受管空正文文档路径"),
    expected_plan: str | None = typer.Option(None, help="预览返回的计划摘要"),
    confirm: bool = typer.Option(False, help="按预览计划写入正文及图片"),
) -> None:
    workspace = ctx.find_root().params.get("workspace")
    emit(
        invoke(
            lambda: AppContainer.build(workspace).deliver_video(
                bundle,
                draft,
                path,
                confirm=confirm,
                expected_plan=expected_plan,
            )
        )
    )
