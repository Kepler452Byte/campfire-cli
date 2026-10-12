"""Standalone stdlib worker, copied before the installed package is replaced."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def save(path: Path, job: dict[str, Any]) -> None:
    descriptor, filename = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(job, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(filename, path)
    finally:
        Path(filename).unlink(missing_ok=True)


def wait_for_host(pid: int, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise OSError("Cannot verify host process exit")
        try:
            if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
                raise TimeoutError("Host process did not exit")
        finally:
            kernel.CloseHandle(handle)
        return
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    raise TimeoutError("Host process did not exit")


def invoke(argv: list[str]) -> dict[str, Any]:
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    payload = json.loads(result.stdout or result.stderr)
    if not isinstance(payload, dict):
        raise ValueError("Invalid new CLI result")
    return payload


def run(path: Path, *, wait: bool = True) -> None:
    job = json.loads(path.read_text(encoding="utf-8"))
    try:
        job["state"] = "waiting"
        save(path, job)
        if wait:
            wait_for_host(job["host_pid"])
        job.update(state="running", package_stage="running")
        save(path, job)
        result = subprocess.run(
            job["update_command"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=900,
            env={**os.environ, **job.get("manager_environment", {})},
        )
        job["manager_exit_code"] = result.returncode
        print("Package manager exit code: " + str(result.returncode))
        print(result.stdout.decode("utf-8", errors="replace"))
        print(result.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        if result.returncode:
            raise RuntimeError("Package manager returned a nonzero exit code")
        version = invoke([job["entry_point"], "--version"])
        if version.get("package") != job["package"] or not isinstance(version.get("version"), str):
            raise ValueError("Installed package identity could not be verified")
        if job.get("target_version") and version["version"] != job["target_version"]:
            raise ValueError("Installed version differs from the selected release")
        job.update(
            package_stage="completed",
            installed_version=version["version"],
            resource_stage="running",
        )
        save(path, job)
        aligned = invoke([job["entry_point"], "upgrade", "--skip-package"])
        job["resources"] = aligned
        save(path, job)
        if aligned.get("status") != "ok" or aligned.get("version") != version["version"]:
            raise ValueError("New package resource alignment did not complete")
        verified = invoke([job["entry_point"], "upgrade", "--skip-package"])
        job["verification"] = verified
        if verified.get("status") != "ok" or verified.get("version") != version["version"]:
            raise ValueError("Resource verification failed")
        if verified.get("skills", {}).get("operations") or any(
            workspace.get("bases", {}).get("operations")
            for workspace in verified.get("workspaces", [])
        ):
            raise ValueError("Resource verification did not reach a stable state")
        job.update(
            state="completed",
            resource_stage="completed",
            message="Package verified and registered resources aligned",
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(str(exc), file=sys.stderr)
        if job["package_stage"] != "completed":
            job["package_stage"] = "failed"
            job["resource_stage"] = "skipped"
        else:
            job["resource_stage"] = "failed"
        job.update(
            state="failed", message="Upgrade failed; inspect the operation log and retry explicitly"
        )
    save(path, job)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
