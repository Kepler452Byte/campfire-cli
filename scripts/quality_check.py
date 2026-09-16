"""
SPEC:
  name: quality_check
  purpose: 运行本地与 CI 共用的快速或发布质量门禁
  idempotent: true
  side_effects:
    - 发布门禁在临时目录构建并安装包
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def check_tag(version: str) -> None:
    tag = os.environ.get("GITHUB_REF_NAME")
    if tag and tag.startswith("v") and tag != f"v{version}":
        raise SystemExit(f"tag {tag} does not match project version {version}")


def smoke_test_wheel(version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="campfire-quality-") as raw_directory:
        directory = Path(raw_directory)
        dist = directory / "dist"
        environment = directory / "venv"
        run("uv", "build", "--out-dir", str(dist))
        wheels = list(dist.glob("*.whl"))
        source_distributions = list(dist.glob("*.tar.gz"))
        if len(wheels) != 1 or len(source_distributions) != 1:
            raise SystemExit("build must produce exactly one wheel and one source distribution")
        wheel = wheels[0]
        run("uv", "venv", str(environment))
        executable_dir = "Scripts" if os.name == "nt" else "bin"
        python = environment / executable_dir / ("python.exe" if os.name == "nt" else "python")
        campfire = environment / executable_dir / (
            "campfire.exe" if os.name == "nt" else "campfire"
        )
        run("uv", "pip", "install", "--python", str(python), str(wheel))
        installed = subprocess.run(
            [str(campfire), "version"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if installed != version:
            raise SystemExit(f"installed version {installed} does not match {version}")
        output = subprocess.run(
            [str(campfire), "document", "type", "list"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        json.loads(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    arguments = parser.parse_args()
    run("uv", "run", "ruff", "check", "src", "tests", "scripts")
    run("uv", "run", "pytest", "-q")
    if arguments.release:
        version = project_version()
        check_tag(version)
        smoke_test_wheel(version)


if __name__ == "__main__":
    main()
