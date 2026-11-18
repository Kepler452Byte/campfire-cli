"""Start a runner with a readiness handshake before releasing it to execute."""

import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import suppress
from pathlib import Path

from campfire_cli.common.exceptions import JobError
from campfire_cli.common.process import no_window_flags


def start_detached(home: Path, job_id: str, expected: str) -> dict:
    flags = no_window_flags()
    if os.name == "nt":
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        [sys.executable, "-m", "campfire_cli.app.job.service.job_worker", job_id, expected],
        env={**os.environ, "CAMPFIRE_HOME": str(home), "PYTHONUTF8": "1"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
        creationflags=flags,
    )
    replies: queue.Queue = queue.Queue(maxsize=1)

    def read_reply():
        try:
            replies.put(process.stdout.readline())
        except OSError:
            replies.put(b"")

    threading.Thread(target=read_reply, daemon=True).start()
    result = None
    acknowledged = False
    try:
        try:
            raw = replies.get(timeout=30)
            result = json.loads(raw)
        except (queue.Empty, ValueError) as exc:
            raise JobError(
                "start-failed", "Runner did not confirm startup; inspect environment"
            ) from exc
        if result.get("status") != "ok":
            details = {
                key: value
                for key, value in result.items()
                if key not in {"status", "code", "message"}
            }
            raise JobError(
                result.get("code", "start-failed"),
                result.get("message", "Startup failed"),
                **details,
            )
        process.stdin.write(b"execute\n")
        process.stdin.flush()
        acknowledged = True
        return {**result, "write_performed": True}
    finally:
        with suppress(OSError):
            process.stdin.close()
        # The worker waits for acknowledgement before invoking any user command.
        if not acknowledged:
            if result is None and process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        else:
            threading.Thread(target=process.wait, daemon=True).start()
        # Closing a pipe before a blocked reader exits can itself block on its I/O lock.
        process.stdout.close()
