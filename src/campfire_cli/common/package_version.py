from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

PYPI_INDEX_URL = "https://pypi.org/pypi/{package}/json"
REQUEST_TIMEOUT_SECONDS = 3.0


def fetch_latest_version(package: str) -> str | None:
    """返回包在 PyPI 的最新发布版本。

    网络不可用或响应异常时返回 None；本查询尽力而为，绝不阻塞或失败上层命令。
    """
    try:
        with urllib.request.urlopen(
            PYPI_INDEX_URL.format(package=package), timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    version = payload.get("info", {}).get("version")
    return version if isinstance(version, str) else None


def is_newer_version(candidate: str, current: str) -> bool:
    """按点分段数值比较版本号，candidate 大于 current 时返回 True。

    段不可数值化时退化为字符串不等比较，例如本地装了 dev 版本。
    """

    def segments(value: str) -> tuple[int | str, ...]:
        return tuple(int(part) if part.isdigit() else part for part in value.strip().split("."))

    try:
        return segments(candidate) > segments(current)
    except TypeError:
        return candidate != current


@dataclass(frozen=True)
class InstallMethod:
    """当前 campfire 安装方式的检测结果与对应的更新命令。"""

    manager: str  # editable / uv-tool / pipx / unknown
    update_command: list[str] | None

    @property
    def hint(self) -> str | None:
        if self.manager == "editable":
            return "当前为源码 editable 安装；请在仓库目录执行 git pull 后重新安装/同步"
        if self.manager == "unknown":
            return "无法识别安装方式；请用原安装渠道更新（uv tool / pipx / pip）"
        return None


def classify_prefix(prefix: str) -> str:
    """按 venv 路径特征识别包管理器：uv tool 与 pipx 的 venv 目录有稳定标记。"""
    parts = [part.casefold() for part in os.path.normpath(prefix).split(os.sep)]
    if "uv" in parts and "tools" in parts:
        return "uv-tool"
    if "pipx" in parts and "venvs" in parts:
        return "pipx"
    return "unknown"


def is_editable_install(package: str) -> bool:
    """读取 dist-info 的 direct_url.json 判断是否 editable 安装。"""
    try:
        direct_url = metadata.distribution(package).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return False
    if not direct_url:
        return False
    try:
        return bool(json.loads(direct_url).get("dir_info", {}).get("editable"))
    except ValueError:
        return False


def detect_install_method(package: str) -> InstallMethod:
    if is_editable_install(package):
        return InstallMethod(manager="editable", update_command=None)
    manager = classify_prefix(sys.prefix)
    if manager == "uv-tool":
        return InstallMethod(manager=manager, update_command=["uv", "tool", "upgrade", package])
    if manager == "pipx":
        return InstallMethod(manager=manager, update_command=["pipx", "upgrade", package])
    return InstallMethod(manager=manager, update_command=None)


def build_updater_script(update_command: list[str], align_command: list[str], pid: int) -> str:
    """构造幂等更新脚本：等待指定进程退出，更新包，成功后对齐治理资源。

    更新必须等待宿主进程退出后执行：Windows 锁定运行中的解释器与可执行文件，
    包管理器无法原地替换正在运行的安装。
    """
    joined_update = " ".join(update_command)
    joined_align = " ".join(align_command)
    if os.name == "nt":
        return (
            f"while (Get-Process -Id {pid} -ErrorAction SilentlyContinue) "
            "{ Start-Sleep -Milliseconds 200 }; "
            f"{joined_update}; if ($LASTEXITCODE -eq 0) {{ {joined_align} }}"
        )
    return f"while kill -0 {pid} 2>/dev/null; do sleep 0.2; done; {joined_update} && {joined_align}"


def default_align_command() -> list[str] | None:
    """更新完成后由新版 CLI 执行的资源对齐命令；找不到入口时返回 None。"""
    executable = shutil.which("campfire") or (sys.argv[0] if sys.argv[0] else None)
    if not executable:
        return None
    return [str(Path(executable).resolve()), "upgrade", "--skip-package"]


def spawn_detached_updater(update_command: list[str], align_command: list[str]) -> str:
    """启动脱离当前进程生命周期的更新器，返回其脚本内容供结果展示。"""
    script = build_updater_script(update_command, align_command, os.getpid())
    if os.name == "nt":
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    else:
        args = ["/bin/sh", "-c", script]
    subprocess.Popen(args, stdin=subprocess.DEVNULL)
    return script
