from __future__ import annotations

import json
import urllib.request
from importlib import metadata

from packaging.version import InvalidVersion, Version

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
    info = payload.get("info") if isinstance(payload, dict) else None
    version = info.get("version") if isinstance(info, dict) else None
    return version if isinstance(version, str) else None


def is_newer_version(candidate: str, current: str) -> bool:
    """Compare Python release versions; ignore invalid remote or installed versions."""
    try:
        return Version(candidate) > Version(current)
    except InvalidVersion:
        return False


def installed_version() -> str:
    return metadata.version("campfire-cli")
