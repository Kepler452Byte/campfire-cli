"""SPEC:
name: pypi_verify
purpose: 有限等待公共 PyPI 安装可用，并验证已发布版本
idempotent: true
side_effects:
  - 在临时虚拟环境安装已发布的包，不构建或上传产物
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import time
from pathlib import Path


def verify(version: str, environment: Path) -> None:
    """Retry installation for at most three minutes; never retry a version mismatch."""
    subprocess.run(["uv", "venv", str(environment)], check=True)
    bin_dir = environment / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    campfire = bin_dir / ("campfire.exe" if os.name == "nt" else "campfire")
    command = [
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--refresh",
        "--index-url",
        "https://pypi.org/simple",
        f"campfire-cli=={version}",
    ]
    deadline = time.monotonic() + 180
    while True:
        try:
            subprocess.run(command, check=True, timeout=max(0.001, deadline - time.monotonic()))
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            remaining = deadline - time.monotonic()
            if remaining <= 15:
                raise
            print("PyPI installation unavailable; retrying in 15 seconds", flush=True)
            time.sleep(15)
    installed = subprocess.run(
        [str(campfire), "version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    if installed != version:
        raise SystemExit(f"installed version {installed} does not match {version}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="campfire-pypi-") as directory:
        verify(args.version, Path(directory) / "venv")


if __name__ == "__main__":
    main()
