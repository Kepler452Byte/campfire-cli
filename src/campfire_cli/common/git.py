from __future__ import annotations

import os
import subprocess
from pathlib import Path


class GitCommandError(Exception):
    """A Git operation failed or timed out without exposing credential-bearing output."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def run_git(root: Path, *arguments: str) -> str:
    """Run Git noninteractively, capturing output with a bounded execution time."""
    environment = os.environ.copy()
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_MERGE_AUTOEDIT="no", GCM_INTERACTIVE="never")
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "color.ui=false",
                "-c",
                "rerere.enabled=false",
                *arguments,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitCommandError("Git unavailable or operation timed out") from exc
    if result.returncode:
        raise GitCommandError("Git operation failed")
    return result.stdout
