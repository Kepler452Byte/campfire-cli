"""Serve packaged browser assets and authenticated local APIs."""

import asyncio
import socket
import webbrowser
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from campfire_cli.common.cli_output import emit
from campfire_cli.common.exceptions import AppError, JobError
from campfire_cli.common.filesystem.process_lock import process_lock
from campfire_cli.container import AppContainer
from campfire_cli.web.api.jobs import router
from campfire_cli.web.exceptions import app_error_handler, envelope, validation_handler
from campfire_cli.web.security import LocalAccess


class SessionInput(BaseModel):
    ticket: str


def create_app(*, build_job=AppContainer.build_job, assets: Path | None = None) -> FastAPI:
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
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
        if request.url.path.startswith("/api/"):
            denied = application.state.access.check(request)
            if denied:
                status, code = denied
                return envelope(
                    {
                        "status": "error",
                        "code": code,
                        "message": "Open the current local connection link",
                    },
                    status,
                )
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

    @application.post("/api/session")
    def session(body: SessionInput):
        if not application.state.access.exchange(body.ticket):
            return envelope(
                {
                    "status": "error",
                    "code": "invalid-ticket",
                    "message": "The connection link is invalid or already used",
                },
                401,
            )
        response = envelope({"status": "ok"})
        response.set_cookie(
            "campfire_session",
            application.state.access.session,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    application.include_router(router)

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


def serve(port: int, no_open: bool) -> None:
    import uvicorn

    service = AppContainer.build_job()
    try:
        with service.lock():
            service.check_upgrade()
            lease = process_lock(service.home / "jobs/locks/web.lock")
            lease.__enter__()
        try:
            application = create_app()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", port))
                listener.listen(128)
                address = f"http://127.0.0.1:{listener.getsockname()[1]}"
                url = f"{address}/#connect={application.state.access.ticket}"
                server = uvicorn.Server(
                    uvicorn.Config(
                        application,
                        log_config=None,
                        access_log=False,
                        log_level="critical",
                    )
                )

                async def run():
                    task = asyncio.create_task(server.serve(sockets=[listener]))
                    while not server.started and not task.done():
                        await asyncio.sleep(0.01)
                    if not server.started:
                        await task
                        raise JobError("web-start-failed", "Web server did not start")
                    emit(
                        {
                            "status": "ok",
                            "url": url,
                            "address": address,
                            "hint": "Keep this process running; Ctrl+C stops the Web, not Jobs",
                        }
                    )
                    if not no_open:
                        with suppress(OSError):
                            await asyncio.to_thread(webbrowser.open, url)
                    await task

                asyncio.run(run())
        finally:
            lease.__exit__(None, None, None)
    finally:
        service.runs.close()
