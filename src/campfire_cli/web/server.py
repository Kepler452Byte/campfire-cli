"""Serve packaged browser assets and authenticated local APIs."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException
from starlette.types import Lifespan

from campfire_cli.common.exceptions import AppError
from campfire_cli.container import AppContainer
from campfire_cli.web.api.jobs import router
from campfire_cli.web.api.scripts import router as script_router
from campfire_cli.web.api.session import router as session_router
from campfire_cli.web.exceptions import app_error_handler, envelope, validation_handler
from campfire_cli.web.security import LocalAccess


def create_app(
    *,
    build_job=AppContainer.build_job,
    assets: Path | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    application.state.build_job = build_job
    application.state.access = LocalAccess()
    assets = assets or Path(__file__).resolve().parents[1] / "resources/web"
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, validation_handler)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return envelope(
            {
                "status": "error",
                "code": "internal-error",
                "message": "Unexpected failure; inspect current task and execution state",
            },
            500,
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return envelope(
            {"status": "error", "code": "http-error", "message": str(exc.detail)}, exc.status_code
        )

    @application.middleware("http")
    async def protect(request: Request, call_next):
        denied = (
            application.state.access.check(request)
            if request.url.path.startswith("/api/")
            else None
        )
        if denied:
            status, code = denied
            response = envelope(
                {
                    "status": "error",
                    "code": code,
                    "message": "Open the current local connection link",
                },
                status,
            )
        else:
            response = await call_next(request)
        response.headers.update(
            {
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            }
        )
        return response

    application.include_router(session_router)
    application.include_router(router)
    application.include_router(script_router)

    @application.get("/{path:path}")
    def page(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route does not exist")
        target = (assets / path).resolve()
        if not target.is_relative_to(assets.resolve()):
            raise HTTPException(404, "Asset does not exist")
        if target.is_file():
            return FileResponse(target)
        if path.startswith("assets/") or Path(path).suffix:
            raise HTTPException(404, "Asset does not exist")
        if not (assets / "index.html").is_file():
            raise HTTPException(503, "Packaged web assets are missing; build or reinstall Campfire")
        return FileResponse(assets / "index.html")

    return application
