"""Scope application services to one HTTP request."""

from collections.abc import Iterator

from fastapi import Request

from campfire_cli.app.job.service.job_service import JobService


def job_service(request: Request) -> Iterator[JobService]:
    service = request.app.state.build_job()
    try:
        yield service
    finally:
        service.runs.close()
