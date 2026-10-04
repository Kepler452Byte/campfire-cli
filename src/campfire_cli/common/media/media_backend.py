from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import suppress

import psutil

from campfire_cli.common.exceptions import AppError


class ProcessMediaBackend:
    """Run optional native decoders outside the CLI with a bounded lifetime."""

    def run(self, request: dict, timeout: int) -> dict:
        process = subprocess.Popen(
            [sys.executable, "-m", "campfire_cli.common.media.media_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        )
        try:
            stdout, stderr = process.communicate(json.dumps(request), timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            children = []
            with suppress(psutil.NoSuchProcess):
                children = psutil.Process(process.pid).children(recursive=True)
            for child in reversed(children):
                with suppress(psutil.NoSuchProcess):
                    child.kill()
            process.kill()
            process.communicate()
            raise AppError(
                "媒体处理已取消或超时；原视频未修改",
                code="video-timeout" if isinstance(exc, subprocess.TimeoutExpired) else "cancelled",
            ) from exc
        if process.returncode:
            raise AppError(
                "本地媒体处理失败", code="video-processing-failed", detail=stderr[-2000:]
            )
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise AppError("媒体处理结果无效", code="video-invalid-result") from exc
