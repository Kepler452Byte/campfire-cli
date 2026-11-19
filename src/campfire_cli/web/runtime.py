"""Own the local Web process and its upgrade lease."""

import asyncio
import os
import socket
import webbrowser
from contextlib import asynccontextmanager, suppress

from campfire_cli.common.cli_output import emit
from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem.process_lock import process_lock
from campfire_cli.container import AppContainer
from campfire_cli.web.connection import WebConnection
from campfire_cli.web.server import create_app


def serve(port: int, no_open: bool) -> None:
    import uvicorn

    service = AppContainer.build_job()
    try:
        with service.lock():
            service.check_upgrade()
            lease = process_lock(service.home / "jobs/locks/web.lock")
            try:
                lease.__enter__()
            except JobError as exc:
                if exc.code != "busy":
                    raise
                lease = None
        registration = service.home / "web.json"
        if lease is None:
            result = WebConnection.read(registration).link(port)
            emit(result)
            if not no_open:
                with suppress(OSError):
                    webbrowser.open(result["url"])
            return
        try:

            @asynccontextmanager
            async def lifespan(application):
                try:
                    yield
                finally:
                    registration.unlink(missing_ok=True)

            application = create_app(lifespan=lifespan)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_EXCLUSIVEADDRUSE if os.name == "nt" else socket.SO_REUSEADDR,
                    1,
                )
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
                    WebConnection(
                        listener.getsockname()[1], os.getpid(), application.state.access.control
                    ).write(registration)
                    emit(
                        {
                            "status": "ok",
                            "action": "started",
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
