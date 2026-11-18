"""HTTP delivery for bounded, read-only script project browsing."""

from typing import Annotated

from fastapi import APIRouter, Depends

from campfire_cli.app.script.service.script_service import ScriptService
from campfire_cli.container import AppContainer
from campfire_cli.web.exceptions import envelope

router = APIRouter(prefix="/api/v1/scripts")


def script_service() -> ScriptService:
    return AppContainer.build_script()


Service = Annotated[ScriptService, Depends(script_service)]


@router.get("")
def projects(service: Service):
    return envelope(service.projects())


@router.get("/{project}/tree")
def directory(project: str, service: Service, path: str = ""):
    return envelope(service.directory(project, path))


@router.get("/{project}/file")
def file(project: str, path: str, service: Service):
    return envelope(service.file(project, path))
