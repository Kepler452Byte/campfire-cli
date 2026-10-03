from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import resolution, selector
from campfire_cli.app.workspace.service.structure_service import DomainService
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer

domain_cli = typer.Typer(
    help="管理 Space 内可嵌套的内容领域", context_settings={"help_option_names": ["-h", "--help"]}
)


def service(ctx: typer.Context) -> DomainService:
    resolved = resolution(ctx)
    return DomainService(Path(resolved.workspace), campfire_home())


def applications(ctx: typer.Context) -> AppContainer:
    return AppContainer.build(selector(ctx))


@domain_cli.command("list")
def list_domains(
    ctx: typer.Context,
    space: str | None = typer.Option(None, "--space"),
    project: str | None = typer.Option(None, "--project"),
) -> None:
    emit(invoke(lambda: service(ctx).list(space, project)))


@domain_cli.command("show")
def show(ctx: typer.Context, domain_id: str) -> None:
    emit(invoke(lambda: service(ctx).show(domain_id)))


@domain_cli.command("check")
def check(ctx: typer.Context) -> None:
    emit(invoke(lambda: service(ctx).check()))


@domain_cli.command("format")
def format_domain(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain", help="要格式化的 Domain id"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """只规范化 Domain 声明 Frontmatter，完整保留 Markdown 正文。"""
    emit(invoke(lambda: service(ctx).format(domain_id, confirm)))


@domain_cli.command("create")
def create(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--id", help="稳定 Domain id"),
    name: str = typer.Option(..., "--name", help="Domain 显示名称"),
    path: str = typer.Option(..., "--path", help="待创建 Domain 的 Workspace 相对路径"),
    domain_type: str = typer.Option(..., "--type", help="Domain 类型"),
    governance: str | None = typer.Option(
        None, "--governance", help="根 Domain 必填；嵌套 Domain 自动继承"
    ),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(
        invoke(
            lambda: service(ctx).create(
                domain_id=domain_id,
                name=name,
                path=path,
                domain_type=domain_type,
                governance=governance,
                project_id=None,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("adopt")
def adopt(
    ctx: typer.Context,
    source: Path = typer.Option(..., "--source", help="待接管目录；可位于 Workspace 外"),
    domain_id: str = typer.Option(..., "--id", help="稳定 Domain id"),
    name: str = typer.Option(..., "--name", help="Domain 显示名称"),
    target_path: str | None = typer.Option(
        None, "--target-path", help="外部来源必填；内部来源省略时原地接管"
    ),
    domain_type: str = typer.Option(..., "--type", help="Domain 类型"),
    governance: str | None = typer.Option(
        None, "--governance", help="根 Domain 必填；嵌套 Domain 自动继承"
    ),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(
        invoke(
            lambda: applications(ctx).adoption.adopt(
                source,
                domain_id=domain_id,
                name=name,
                target_path=target_path,
                domain_type=domain_type,
                governance=governance,
                project_id=None,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("rename")
def rename(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    name: str | None = typer.Option(None, "--name", help="只修改显示名称"),
    folder_name: str | None = typer.Option(
        None, "--folder-name", help="原父级内的新目录名，不改稳定 id"
    ),
    expected_plan: str | None = typer.Option(
        None, "--expected-plan", help="目录改名确认需带回预览摘要"
    ),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """分别或同时修改 Domain 显示名称、目录名，不改变身份和 Project 绑定。"""
    emit(
        invoke(
            lambda: applications(ctx).domain_restructure.rename(
                domain_id,
                name,
                folder_name=folder_name,
                expected_plan=expected_plan,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("move")
def move(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    target: str = typer.Option(..., "--target", help="目标 Space 或 Domain 的稳定 id"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """把完整 Domain 移入目标 Space 或 Domain，并更新关联事实。"""
    emit(
        invoke(
            lambda: applications(ctx).domain_restructure.move(
                domain_id,
                target,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("rekey")
def rekey(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    new_id: str = typer.Option(..., "--new-id"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """高风险修改稳定 domain_id，并更新直接子领域引用。"""
    emit(
        invoke(
            lambda: applications(ctx).domain_restructure.rekey(domain_id, new_id, confirm=confirm)
        )
    )


@domain_cli.command("merge")
def merge(
    ctx: typer.Context,
    source: str = typer.Option(..., "--source", help="待移除的源 Domain id"),
    target: str = typer.Option(..., "--target", help="接收内容的目标 Domain id"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """把源 Domain 原子合并到目标 Domain；默认只预览。"""
    emit(
        invoke(lambda: applications(ctx).domain_restructure.merge(source, target, confirm=confirm))
    )


@domain_cli.command("delete")
def delete(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """删除逻辑空 Domain；默认只预览且不支持递归删除。"""
    emit(invoke(lambda: applications(ctx).domain_restructure.delete(domain_id, confirm=confirm)))
