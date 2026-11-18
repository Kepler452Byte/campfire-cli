"""HTTP delivery for local job configuration and execution history."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, StrictBool

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.app.job.service.job_service import JobService
from campfire_cli.common.exceptions import InputError
from campfire_cli.common.package_version import installed_version
from campfire_cli.container import AppContainer
from campfire_cli.web.dependencies import job_service
from campfire_cli.web.exceptions import envelope

router = APIRouter(prefix="/api/v1")
Service = Annotated[JobService, Depends(job_service)]


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job: dict | None = None
    confirm: StrictBool = False
    expected_plan: str | None = None


@router.get("/environment")
def environment(service: Service):
    return envelope(
        {"status": "ok", "environment": service.environment(), "version": installed_version()}
    )


@router.get("/workspaces")
def workspaces():
    result = AppContainer.build_workspace().list().model_dump(mode="json")
    return envelope({"status": "ok", **result})


@router.get("/jobs")
def jobs(
    service: Service,
    name: str = "",
    workspace_id: str | None = None,
    state: str | None = None,
    unbound: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    return envelope(
        service.query_jobs(
            name=name,
            workspace_id=workspace_id,
            state=state,
            unbound=unbound,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/jobs/{identity}")
def show(identity: str, service: Service):
    return envelope(service.show(identity))


@router.post("/jobs")
def create(body: Mutation, service: Service):
    job = Job.parse(body.job)
    return envelope(service.change("create", job.id, job, body.confirm, body.expected_plan))


@router.put("/jobs/{identity}")
def update(identity: str, body: Mutation, service: Service):
    job = Job.parse(body.job)
    if job.id != identity:
        raise InputError("Path and Job id must match")
    return envelope(service.change("update", identity, job, body.confirm, body.expected_plan))


@router.post("/jobs/{identity}/run")
def run(identity: str, body: Mutation, service: Service):
    if not body.confirm:
        return envelope(service.run(identity, False))
    return envelope(service.start_run(identity, body.expected_plan or ""), 202)


@router.post("/jobs/{identity}/{action}")
def change(identity: str, action: str, body: Mutation, service: Service):
    if action not in {"pause", "resume", "delete"}:
        raise InputError("Unknown job action", code="not-found")
    if body.job is not None:
        raise InputError("This action does not accept a Job definition")
    return envelope(service.change(action, identity, None, body.confirm, body.expected_plan))


@router.get("/jobs/{identity}/runs")
def history(
    identity: str,
    service: Service,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    service.get(identity)
    return envelope(service.history_page(identity, page, page_size))


@router.get("/runs/{run_id}")
def result(run_id: str, service: Service):
    return envelope({"status": "ok", "run": service.result(run_id, "local")})


@router.get("/runs/{run_id}/logs")
def logs(
    run_id: str,
    service: Service,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    return envelope({"status": "ok", **service.logs(run_id, limit, after)})
