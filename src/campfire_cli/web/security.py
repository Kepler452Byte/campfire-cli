"""Authorize local browser sessions without introducing user accounts."""

import secrets
import threading

from starlette.requests import Request


class LocalAccess:
    def __init__(self):
        self._lock = threading.Lock()
        self.ticket: str | None = secrets.token_urlsafe(32)
        self.session = secrets.token_urlsafe(32)

    def exchange(self, ticket: str) -> bool:
        with self._lock:
            if self.ticket is None or not secrets.compare_digest(ticket, self.ticket):
                return False
            self.ticket = None
            return True

    def check(self, request: Request) -> tuple[int, str] | None:
        if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            return 403, "invalid-host"
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return 403, "invalid-origin"
        if request.headers.get("sec-fetch-site") == "cross-site":
            return 403, "invalid-origin"
        if request.method not in {"GET", "HEAD"} and (
            not origin or request.headers.get("x-campfire-request") != "1"
        ):
            return 403, "invalid-origin"
        if request.url.path != "/api/session" and not secrets.compare_digest(
            request.cookies.get("campfire_session", ""), self.session
        ):
            return 401, "session-required"
        return None
