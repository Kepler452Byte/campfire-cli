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
domain_restructure_cli = typer.Typer(
    help="重构领域名称、路径或稳定身份",
    context_settings={"help_option_names": ["-h", "--help"]},
)
restructure_cli.add_typer(domain_restructure_cli, name="domain")


def emit(result: object) -> None:
    payload = result.model_dump(mode="json")
    payload["issues"] = [enrich_issue(issue) for issue in payload.get("issues", [])]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def service(ctx: typer.Context, workspace: str | None):
    selector = workspace or ctx.find_root().params.get("workspace")
    return AppContainer.build(selector).restructure


def domain_service(ctx: typer.Context, workspace: str | None):
    selector = workspace or ctx.find_root().params.get("workspace")
    return AppContainer.build(selector).domain_restructure


@domain_restructure_cli.command("rename")
def rename_domain(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    name: str = typer.Option(..., "--name"),
    rename_directory: bool = typer.Option(False, "--rename-directory"),
    target_path: str | None = typer.Option(None, "--target-path"),
    project_name: str | None = typer.Option(None, "--project-name"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """修改领域显示名称；可显式联动目录和 Project 展示名称。"""
    emit(
        domain_service(ctx, workspace).rename(
            domain_id,
            name,
            rename_directory=rename_directory,
            target_path=target_path,
            project_name=project_name,
            confirm=confirm,
        )
    )


@domain_restructure_cli.command("move")
def move_domain(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    target_path: str = typer.Option(..., "--target-path"),
    parent_domain: str | None = typer.Option(None, "--parent-domain"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """移动完整领域目录，并更新父领域、Project、Manifest 和路径引用。"""
    emit(
        domain_service(ctx, workspace).move(
            domain_id, target_path, parent_domain=parent_domain, confirm=confirm
        )
    )


@domain_restructure_cli.command("rekey")
def rekey_domain(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    new_id: str = typer.Option(..., "--new-id"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """高风险修改稳定 domain_id，并更新直接子领域引用。"""
    emit(domain_service(ctx, workspace).rekey(domain_id, new_id, confirm=confirm))


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
