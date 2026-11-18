"""Translate protocol-neutral business errors without losing their payload."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from campfire_cli.common.exceptions import AppError


def envelope(data: dict, status: int = 200) -> JSONResponse:
    if status < 400 and data.get("status") in {"blocked", "error"}:
        status = 409 if data["status"] == "blocked" else 500
    return JSONResponse(
        {"code": 0 if status < 400 else status, "message": data.get("message", ""), "data": data},
        status_code=status,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    payload = exc.payload()
    code = payload["code"]
    status = 409 if payload["status"] == "blocked" else 422 if exc.exit_code == 2 else 500
    if code == "not-found":
        status = 404
    if code in {"scheduler-unavailable", "environment-missing"}:
        status = 503
    return envelope(payload, status)


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    issues = [{"field": list(error["loc"]), "type": error["type"]} for error in exc.errors()]
    return envelope(
        {
            "status": "error",
            "code": "invalid-input",
            "message": "Request fields are invalid",
            "issues": issues,
        },
        422,
    )
