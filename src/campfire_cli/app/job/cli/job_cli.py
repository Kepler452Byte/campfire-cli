"""JSON delivery adapter for local command execution."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.common.exceptions import InputError
from campfire_cli.container import AppContainer

job_cli = typer.Typer(help="本机命令、原生定时与运行日志；普通 Job 不要求 Workspace")
Confirm = Annotated[bool, typer.Option("--confirm", help="确认本次预览的操作")]
Expected = Annotated[str | None, typer.Option("--expected-plan", help="本次预览的 expected_plan")]
File = Annotated[
    Path,
    typer.Option(
        "--file",
        help=(
            'UTF-8 JSON: {"id":"example","argv":["/absolute/executable","arg"],'
            '"cwd":"/absolute/directory","schedule":{"kind":"manual"},"timeout":3600}。'
            "可选 workspace_id；workspace_root 自动解析。schedule 支持 manual、"
            "interval（seconds 为整分钟 60..86400）、daily（time HH:MM）、"
            "weekly（day mon..sun、time HH:MM），按设备本地时区执行。"
        ),
    ),
]


def deliver(operation) -> None:
    def execute():
        service = AppContainer.build_job()
        try:
            result = operation(service)
            if service.runs.history_rebuilt:
                result["history_rebuilt"] = True
                result["history_notice"] = (
                    "Incompatible run cache rebuilt; old logs are not recoverable"
                )
            return result
        finally:
            service.runs.close()

    emit(invoke(execute))


def load_job(path: Path) -> Job:
    try:
        return Job.parse(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError) as exc:
        raise InputError("--file 必须是可读取的 UTF-8 JSON 文件", code="invalid-job-file") from exc


@job_cli.command("create")
def create(file: File, confirm: Confirm = False, expected_plan: Expected = None):
    """预览并创建 Job；定时 Job 默认暂停，不自动执行。"""
    job = invoke(lambda: load_job(file))
    deliver(lambda service: service.change("create", job.id, job, confirm, expected_plan))


@job_cli.command("update")
def update(file: File, confirm: Confirm = False, expected_plan: Expected = None):
    """预览并更新 Job，保留原生启停状态。"""
    job = invoke(lambda: load_job(file))
    deliver(lambda service: service.change("update", job.id, job, confirm, expected_plan))


@job_cli.command("list")
def list_jobs(ctx: typer.Context):
    """查询本机定义、环境和实际状态；根级 --workspace 可精确筛选 Vault。"""
    deliver(lambda service: service.list_jobs(ctx.find_root().params.get("workspace")))


@job_cli.command("show")
def show(job_id: str):
    """查询一个 Job 的定义和实际原生状态。"""
    deliver(lambda service: service.show(job_id))


@job_cli.command("run")
def run(
    job_id: str,
    confirm: Confirm = False,
    expected_plan: Expected = None,
    scheduled: bool = typer.Option(False, "--scheduled", hidden=True),
    home: Path | None = typer.Option(None, "--home", hidden=True),
):
    """预览并执行当前 Job；执行成功还需核验预期产物。"""
    if home is not None:
        if not scheduled:
            raise InputError("内部 --home 仅供原生调度入口使用")
        os.environ["CAMPFIRE_HOME"] = str(home.expanduser().resolve())
    deliver(lambda service: service.run(job_id, confirm, expected_plan, scheduled))


@job_cli.command("pause")
def pause(job_id: str, confirm: Confirm = False, expected_plan: Expected = None):
    """预览并暂停定时 Job。"""
    deliver(lambda service: service.change("pause", job_id, None, confirm, expected_plan))


@job_cli.command("resume")
def resume(job_id: str, confirm: Confirm = False, expected_plan: Expected = None):
    """预览并启用定时 Job；manual 不适用。"""
    deliver(lambda service: service.change("resume", job_id, None, confirm, expected_plan))


@job_cli.command("delete")
def delete_job(job_id: str, confirm: Confirm = False, expected_plan: Expected = None):
    """预览并删除 Job 及受管原生入口；运行中拒绝删除。"""
    deliver(lambda service: service.change("delete", job_id, None, confirm, expected_plan))


@job_cli.command("doctor")
def doctor():
    """只读诊断原生调度器和用户会话，不提高系统权限。"""
    deliver(
        lambda service: {
            "status": "ok",
            "environment": service.environment(),
            **service.scheduler.doctor(),
        }
    )


@job_cli.command("history")
def history(
    job: str | None = typer.Option(None, "--job"),
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    offset: int = typer.Option(0, "--offset", min=0),
    timezone: str = typer.Option("UTC", "--timezone", help="UTC、local 或 IANA 时区"),
):
    """分页查询运行历史；进程成功不自动完成任务文档。"""
    deliver(lambda service: {"status": "ok", "runs": service.history(job, limit, offset, timezone)})


@job_cli.command("result")
def result(run_id: str, timezone: str = typer.Option("UTC", "--timezone")):
    """查询本次 Run 的实际退出与耗时。"""
    deliver(lambda service: {"status": "ok", "run": service.result(run_id, timezone)})


@job_cli.command("logs")
def logs(
    run_id: str,
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    after: int = typer.Option(0, "--after", min=0),
):
    """按 seq 游标读取本次 stdout/stderr；truncated 表示达到日志上限。"""
    deliver(lambda service: {"status": "ok", **service.logs(run_id, limit, after)})


@job_cli.command("cleanup")
def cleanup(
    job: str | None = typer.Option(None, "--job"),
    older_than: int | None = typer.Option(
        None, "--older-than", min=0, help="按完成时间的滚动24小时天数；显式指定时覆盖默认保留策略"
    ),
    status: list[str] | None = typer.Option(
        None, "--status", help="可重复：succeeded、failed、timeout、interrupted"
    ),
    keep_failures: bool = typer.Option(False, "--keep-failures"),
    confirm: Confirm = False,
    expected_plan: Expected = None,
):
    """预览并清理已完成历史和日志，不修改定义及调度。"""
    deliver(
        lambda service: service.cleanup(
            job, older_than, status, keep_failures, confirm, expected_plan
        )
    )


@job_cli.command("compact")
def compact(confirm: Confirm = False, expected_plan: Expected = None):
    """预览并回收日志 SQLite 空间；要求没有活动运行。"""
    deliver(lambda service: service.compact(confirm, expected_plan))
