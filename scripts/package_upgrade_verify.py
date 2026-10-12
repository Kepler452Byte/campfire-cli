"""
SPEC:
  name: package_upgrade_verify
  purpose: 隔离验证真实 uv tool 或 pipx 的旧版到当前版后台升级
  idempotent: true
  side_effects:
    - 在临时目录安装旧版本并更新到当前源码，不修改用户安装
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def archive(ref: str, target: Path) -> None:
    data = subprocess.run(["git", "archive", ref], cwd=ROOT, check=True, capture_output=True).stdout
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as content:
        content.extractall(target, filter="data")


def verify(manager: str, baseline: str = "v0.2.5") -> dict:
    with tempfile.TemporaryDirectory(prefix="campfire upgrade ") as raw:
        root = Path(raw).resolve()
        source = root / "source with spaces"
        candidate = root / "candidate"
        archive(baseline, source)
        archive("HEAD", candidate)
        old_version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
        new_version = tomllib.loads((candidate / "pyproject.toml").read_text())["project"][
            "version"
        ]
        environment = {
            **os.environ,
            "UV_TOOL_DIR": str(root / "uv tools"),
            "UV_TOOL_BIN_DIR": str(root / "uv bin"),
            "PIPX_HOME": str(root / "pipx home"),
            "PIPX_BIN_DIR": str(root / "pipx bin"),
            "CAMPFIRE_HOME": str(root / "state"),
            "CAMPFIRE_SKILL_TARGETS": str(root / "skills"),
            "CAMPFIRE_AGENT_HINT_PATH": str(root / "hint.md"),
            "PYTHONIOENCODING": "utf-8",
        }
        environment.pop("PYTHONPATH", None)
        executable = shutil.which("uv" if manager == "uv-tool" else "pipx")
        if not executable:
            raise RuntimeError(f"Missing installer: {manager}")
        command = (
            [executable, "tool", "install", "--python", sys.executable, str(source)]
            if manager == "uv-tool"
            else [executable, "install", "--python", sys.executable, str(source)]
        )
        subprocess.run(command, env=environment, check=True, timeout=240)
        prefix = (
            root / "uv tools" / "campfire-cli"
            if manager == "uv-tool"
            else root / "pipx home" / "venvs" / "campfire-cli"
        )
        python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        shutil.rmtree(source)
        shutil.copytree(candidate, source)
        host = (
            "import sys,json,os\nfrom pathlib import Path\n"
            f"sys.path.insert(0,{str(candidate / 'src')!r})\n"
            "from campfire_cli.common.package_updater import PackageUpdater,plan_digest\n"
            "updater=PackageUpdater('campfire-cli','campfire',Path(os.environ['CAMPFIRE_HOME']))\n"
            "plan=updater.plan()\n"
            f"assert plan['manager']=={manager!r} and plan['supported'],plan\n"
            f"assert plan['current_version']=={old_version!r},plan\n"
            f"plan['target_version']={new_version!r}\n"
            "print(json.dumps(updater.start(plan,plan_digest(plan))))\n"
        )
        started = subprocess.run(
            [str(python), "-c", host],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if started.returncode:
            raise RuntimeError(started.stderr or started.stdout)
        operation = json.loads(started.stdout)
        result_path = root / "state" / "upgrades" / operation["operation_id"] / "result.json"
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            result = json.loads(result_path.read_bytes())
            if result["state"] in {"completed", "failed"}:
                break
            time.sleep(0.2)
        if result["state"] != "completed":
            raise RuntimeError(Path(operation["log_path"]).read_text(encoding="utf-8"))
        assert result["installed_version"] == new_version, result
        assert result["package_stage"] == result["resource_stage"] == "completed", result
        return {
            "manager": manager,
            "from_version": old_version,
            "version": new_version,
            "state": result["state"],
            "package_stage": result["package_stage"],
            "resource_stage": result["resource_stage"],
            "spaces_in_paths": True,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manager", required=True, choices=["uv-tool", "pipx"])
    parser.add_argument("--baseline", default="v0.2.5")
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.manager, arguments.baseline), ensure_ascii=False, indent=2))
