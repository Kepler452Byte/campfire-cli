"""Own the local Web process and its upgrade lease."""

import asyncio
import socket
import webbrowser
from contextlib import suppress

from campfire_cli.common.cli_output import emit
from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem.process_lock import process_lock
from campfire_cli.container import AppContainer
from campfire_cli.web.server import create_app


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
