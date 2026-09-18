from __future__ import annotations

import typer

from campfire_cli.app.document.cli.profile_cli import profile_cli
from campfire_cli.app.document.cli.type_cli import type_cli
from campfire_cli.app.document.schema import DocumentApplyRequest
from campfire_cli.app.document.service.document_service import DocumentService
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.common.exceptions import InputError

document_cli = typer.Typer(
    help="创建、检查和维护文档及其规则",
    context_settings={"help_option_names": ["-h", "--help"]},
)
document_cli.add_typer(profile_cli, name="profile")
document_cli.add_typer(type_cli, name="type")

SET_OPTION_HELP = (
    "设置 Frontmatter 字段，格式 field=value，可重复使用。"
    "值类型由有效 Profile 决定；列表使用严格 JSON，例如 "
    '--set \'tags=["tag1","tag2"]\'。'
)
PATH_OPTION_HELP = "Workspace 根目录相对路径（不是 cwd 相对路径），或 Workspace 内绝对路径"


def service(ctx: typer.Context) -> DocumentService:
    from campfire_cli.container import AppContainer

    selector = ctx.find_root().params.get("workspace")
    return AppContainer.build(selector).document


@document_cli.command("check")
def check(
    ctx: typer.Context, path: str = typer.Option(..., "--path", help=PATH_OPTION_HELP)
) -> None:
    """检查一篇 Markdown 文档是否符合当前类型与 Profile 契约。"""
    emit(invoke(lambda: service(ctx).check(path)))


@document_cli.command("kanban-check")
def kanban_check(
    ctx: typer.Context, path: str = typer.Option(..., "--path", help=PATH_OPTION_HELP)
) -> None:
    """检查文档是否满足 Obsidian Kanban 插件的渲染契约。"""
    emit(invoke(lambda: service(ctx).kanban_check(path)))


@document_cli.command("inspect")
def inspect(
    ctx: typer.Context, path: str = typer.Option(..., "--path", help=PATH_OPTION_HELP)
) -> None:
    """返回单篇文档的 Profile、领域、确定关系和问题上下文。

    示例：campfire document inspect --path "mywork/项目/记录-进展.md"
    """
    emit(invoke(lambda: service(ctx).inspect(path)))


@document_cli.command("list")
def list_documents(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", help="精确 Project id"),
    domain: str | None = typer.Option(None, "--domain", help="精确 Domain id"),
    document_type: str | None = typer.Option(None, "--type", help="精确文档类型"),
    document_status: str | None = typer.Option(None, "--document-status"),
    task_status: str | None = typer.Option(None, "--task-status"),
    limit: int | None = typer.Option(None, "--limit", min=1),
) -> None:
    """按 Project、Domain、类型与状态列出受管内容文档。"""
    emit(
        invoke(
            lambda: service(ctx).list(
                project=project,
                domain=domain,
                document_type=document_type,
                document_status=document_status,
                task_status=task_status,
                limit=limit,
            )
        )
    )


@document_cli.command("format")
def format_document(
    ctx: typer.Context,
    path: str = typer.Option(..., "--path", help=PATH_OPTION_HELP),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览或执行一篇文档的 Frontmatter 字段排序。"""
    emit(invoke(lambda: service(ctx).format(path, confirm)))


def parse_values(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise InputError(
                f"--set 必须使用 field=value：{item}",
                code="invalid-set",
                option="--set",
                actual=item,
            )
        key, raw = item.split("=", 1)
        if not key.strip():
            raise InputError("--set 字段名不能为空", code="invalid-set", option="--set")
        key = key.strip()
        if key in values:
            raise InputError(
                f"--set 字段重复：{key}", code="invalid-set", option="--set", field=key
            )
        values[key] = raw
    return values


@document_cli.command("apply")
def apply_document(
    ctx: typer.Context,
    path: str = typer.Option(
        ...,
        "--path",
        help=PATH_OPTION_HELP + "；创建或唯一更新时可省略 .md，创建时可省略类型前缀",
    ),
    document_type: str | None = typer.Option(None, "--type"),
    set_values: list[str] | None = typer.Option(None, "--set", help=SET_OPTION_HELP),
    expected_hash: str | None = typer.Option(None, "--expected-hash"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览或应用一篇 Profile 合法文档的创建、补丁与显式类型变更。

    示例：campfire document apply --path "mynote/Python/混合编程" --type knowledge

    创建或唯一更新时可省略 .md；创建时也可省略类型前缀。
    CLI 在 normalization 中解释变换，并返回最终 target。
    已有文档的 --type 发生变化时，同一原子操作同步文件名和引用。
    """
    values = invoke(lambda: parse_values(set_values or []))
    emit(
        invoke(
            lambda: service(ctx).apply(
                DocumentApplyRequest(
                    path=path,
                    document_type=document_type,
                    values=values,
                    expected_hash=expected_hash,
                    confirm=confirm,
                )
            )
        )
    )


@document_cli.command("move")
def move_document(
    ctx: typer.Context,
    source: str = typer.Option(..., "--path", help=PATH_OPTION_HELP),
    target_domain: str = typer.Option(..., "--domain", help="目标 Domain 的稳定 id"),
    name: str | None = typer.Option(None, "--name", help="可选的新文件名；省略时保持原文件名"),
    set_values: list[str] | None = typer.Option(None, "--set", help=SET_OPTION_HELP),
    unset_fields: list[str] | None = typer.Option(None, "--unset"),
    expected_hash: str | None = typer.Option(None, "--expected-hash"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览或移动一篇文档，并按目标 Domain 契约更新归属与引用。"""
    values = invoke(lambda: parse_values(set_values or []))
    emit(
        invoke(
            lambda: service(ctx).move(
                source,
                target_domain,
                name=name,
                values=values,
                unset_fields=tuple(unset_fields or []),
                expected_hash=expected_hash,
                confirm=confirm,
            )
        )
    )


@document_cli.command("rename")
def rename_document(
    ctx: typer.Context,
    source: str = typer.Option(..., "--path", help=PATH_OPTION_HELP),
    name: str = typer.Option(..., "--name", help="新标题；不含类型前缀和 .md 后缀"),
    expected_hash: str | None = typer.Option(None, "--expected-hash"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预览或原地改名一篇文档，并同步标题、文件名与受管引用。"""
    emit(
        invoke(
            lambda: service(ctx).rename(
                source,
                name,
                expected_hash=expected_hash,
                confirm=confirm,
            )
        )
    )
