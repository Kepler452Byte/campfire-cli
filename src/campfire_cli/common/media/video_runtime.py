from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from campfire_cli.common.exceptions import AppError, GovernanceBlockedError


class LocalVideoRuntime:
    """Install missing video dependencies in the current isolated Python environment."""

    def plan(self) -> dict:
        requirements = []
        for value in metadata.requires("campfire-cli") or []:
            requirement = Requirement(value)
            if (
                requirement.marker
                and requirement.marker.evaluate({"extra": "video"})
                and not requirement.marker.evaluate({"extra": ""})
            ):
                requirement.marker = None
                requirements.append(str(requirement))
        if not requirements:
            raise AppError("安装元数据缺少 video extra；请修复 Campfire 安装")
        installed = {
            canonicalize_name(dist.metadata["Name"]): dist.version
            for dist in metadata.distributions()
            if dist.metadata["Name"]
        }
        pending = list(requirements)
        seen = set()
        missing = set()
        while pending:
            value = pending.pop()
            if value in seen:
                continue
            seen.add(value)
            requirement = Requirement(value)
            version = installed.get(canonicalize_name(requirement.name))
            if version is None or not requirement.specifier.contains(version, prereleases=True):
                missing.add(str(requirement))
                continue
            for child in metadata.requires(requirement.name) or []:
                dependency = Requirement(child)
                if dependency.marker is None or any(
                    dependency.marker.evaluate({"extra": extra})
                    for extra in ("", *requirement.extras)
                ):
                    dependency.marker = None
                    pending.append(str(dependency))
        installer = None
        if sys.prefix != sys.base_prefix:
            uv = shutil.which("uv")
            if uv:
                installer = [uv, "pip", "install", "--python", sys.executable]
            elif importlib.util.find_spec("pip") is not None:
                installer = [sys.executable, "-m", "pip", "install"]
        return {
            "python": sys.executable,
            "requirements": sorted(requirements),
            "missing": sorted(missing),
            "installer": installer,
            "constraints": sorted(f"{name}=={version}" for name, version in installed.items()),
        }

    def install(self, plan: dict, timeout: int) -> None:
        if self.plan() != plan:
            raise GovernanceBlockedError("Python 环境已变化；请重新预览 video setup")
        if not plan["missing"]:
            return
        if not plan["installer"]:
            raise AppError("请使用 uv tool、pipx 或 venv 安装 Campfire；不自动修改系统 Python")
        # Pin existing packages so a live CLI never replaces its loaded dependencies.
        with tempfile.TemporaryDirectory(prefix="campfire-video-install-") as directory:
            constraints = Path(directory) / "constraints.txt"
            constraints.write_text("\n".join(plan["constraints"]), encoding="utf-8")
            command = [
                *plan["installer"],
                "--only-binary=:all:",
                "--constraint",
                str(constraints),
                *plan["requirements"],
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise AppError(
                    "视频依赖安装超时；已安装部分保留，重新预览后重试",
                    code="video-install-timeout",
                ) from exc
            if result.returncode:
                raise AppError(
                    "视频依赖安装失败；检查网络、兼容 wheel 或现有版本冲突后重新预览",
                    code="video-install-failed",
                    detail=result.stderr[-2000:],
                )
        importlib.invalidate_caches()
        if self.plan()["missing"]:
            raise AppError(
                "视频依赖尚未完整安装；重新预览 video setup", code="video-install-failed"
            )
