from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import typer

from campfire_cli.common.exceptions import AppError

decision_cli = typer.Typer(
    help="维护需要人类或高级 Agent 回答的持久 Decision",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def emit(result: object) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


def invoke(operation: Callable[[], Any]) -> None:
    try:
        emit(operation())
    except AppError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(exc.exit_code) from exc


@decision_cli.command("create")
def create(
    ctx: typer.Context,
    key: str = typer.Option(..., "--key", help="Workspace 内稳定的幂等键"),
    question: str = typer.Option(..., "--question"),
    source_type: str = typer.Option(..., "--source-type"),
    context: str = typer.Option("", "--context"),
    recommendation: str = typer.Option("", "--recommendation"),
    option: list[str] | None = typer.Option(None, "--option"),
    related_document: list[str] | None = typer.Option(None, "--related-document"),
    source_id: str | None = typer.Option(None, "--source-id"),
    session_provider: str | None = typer.Option(None, "--session-provider"),
    session_id: str | None = typer.Option(None, "--session-id"),
    actor: str | None = typer.Option(None, "--actor"),
) -> None:
    """创建或刷新一个仍处于 pending 的幂等 Decision。"""
    invoke(
        lambda: ctx.obj.decision.create(
            key=key,
            question=question,
            source_type=source_type,
            context=context,
            recommendation=recommendation,
            options=option,
            related_documents=related_document,
            source_id=source_id,
            session_provider=session_provider,
            session_id=session_id,
            actor=actor,
        )
    )


@decision_cli.command("list")
def list_decisions(
    ctx: typer.Context,
    status: str | None = typer.Option(None, "--status"),
) -> None:
    """列出当前 Workspace 的 Decision。"""
    invoke(lambda: ctx.obj.decision.list(status))


@decision_cli.command("show")
def show(ctx: typer.Context, decision_id: str) -> None:
    """显示 Decision 当前内容和完整事件历史。"""
    invoke(lambda: ctx.obj.decision.show(decision_id))


@decision_cli.command("answer")
def answer(
    ctx: typer.Context,
    decision_id: str,
    answer_text: str = typer.Option(..., "--answer"),
    answered_by: str = typer.Option(..., "--answered-by"),
) -> None:
    """回答 pending Decision，并转为 answered。"""
    invoke(lambda: ctx.obj.decision.answer(decision_id, answer_text, answered_by))


@decision_cli.command("close")
def close(
    ctx: typer.Context,
    decision_id: str,
    actor: str | None = typer.Option(None, "--actor"),
) -> None:
    """关闭已经回答且被消费的 Decision。"""
    invoke(lambda: ctx.obj.decision.close(decision_id, actor))


@decision_cli.command("cancel")
def cancel(
    ctx: typer.Context,
    decision_id: str,
    reason: str = typer.Option(..., "--reason"),
    actor: str | None = typer.Option(None, "--actor"),
) -> None:
    """显式取消不再需要回答的 pending Decision。"""
    invoke(lambda: ctx.obj.decision.cancel(decision_id, reason, actor))


@decision_cli.command("sync")
def sync(ctx: typer.Context) -> None:
    """从 SQLite 重建所有 pending Decision 的 Vault 投影。"""
    invoke(ctx.obj.decision.sync)
