"""Discover and reconnect to a Web process owned by the current local user."""

import json
import os
import stat
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem.atomic import atomic_write


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class WebConnection:
    port: int
    pid: int
    control: str = field(repr=False)

    @property
    def address(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def write(self, path: Path) -> None:
        atomic_write(path, json.dumps(asdict(self)))

    @classmethod
    def read(cls, path: Path) -> "WebConnection":
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or (
                    os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077)
                ):
                    raise ValueError("Private runtime file required")
                data = json.loads(stream.read(8192))
            connection = cls(**data)
            if (
                type(connection.port) is not int
                or not 1 <= connection.port <= 65535
                or type(connection.pid) is not int
                or connection.pid <= 0
                or not isinstance(connection.control, str)
                or len(connection.control) != 43
            ):
                raise ValueError("Invalid runtime registration")
            return connection
        except (OSError, ValueError, TypeError) as exc:
            raise JobError(
                "web-connection-unavailable",
                "Web registration is unavailable or not private; wait for startup and retry",
            ) from exc

    def link(self, port: int) -> dict:
        if port and port != self.port:
            raise JobError("web-port-conflict", "Web already runs on another port", port=self.port)
        if not psutil.pid_exists(self.pid):
            raise JobError("web-connection-unavailable", "Registered Web process has stopped")
        request = urllib.request.Request(
            f"{self.address}/api/session/link",
            data=b"",
            headers={"X-Campfire-Control": self.control},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=3) as response:
                result = json.load(response)
            if result["code"] != 0 or result["data"]["status"] != "ok":
                raise ValueError("Connection request rejected")
            ticket = result["data"]["ticket"]
            if not isinstance(ticket, str) or len(ticket) != 43:
                raise ValueError("Invalid connection ticket")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise JobError(
                "web-connection-unavailable",
                "Cannot reconnect to Web; check that it is still running",
            ) from exc
        return {
            "status": "ok",
            "action": "reconnected",
            "address": self.address,
            "url": f"{self.address}/#connect={ticket}",
        }
