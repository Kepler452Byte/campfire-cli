from __future__ import annotations

import json
import urllib.request

PYPI_INDEX_URL = "https://pypi.org/pypi/{package}/json"
REQUEST_TIMEOUT_SECONDS = 3.0


def fetch_latest_version(package: str) -> str | None:
    """查询 PyPI 最新发布版本；网络不可用或响应异常时返回 None（检测尽力而为，不阻塞升级）。"""
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
    """按点分段数值比较版本号；遇到不可数值化的段（如 dev 标记）退化为不等比较。"""

    def segments(value: str) -> tuple[int | str, ...]:
        return tuple(int(part) if part.isdigit() else part for part in value.strip().split("."))

    try:
        return segments(candidate) > segments(current)
    except TypeError:
        return candidate != current
