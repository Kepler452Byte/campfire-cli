"""Exchange a one-use connection ticket for a browser session."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from campfire_cli.web.exceptions import envelope

router = APIRouter()


class SessionInput(BaseModel):
    ticket: str


@router.post("/api/session")
def session(body: SessionInput, request: Request):
    access = request.app.state.access
    if not access.exchange(body.ticket):
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
        "campfire_session", access.session, httponly=True, samesite="strict", path="/"
    )
    return response
