from __future__ import annotations

import os
from copy import deepcopy
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml


@cache
def builtin_config() -> dict[str, Any]:
    """Load the immutable packaged product configuration."""
    resource = files("campfire_cli.resources.defaults").joinpath("config.yml")
    value = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("version"), int):
        raise ValueError("内置 config.yml 缺少整数 version")
    return value


def builtin_section(name: str) -> dict[str, Any]:
    value = builtin_config().get(name)
    if not isinstance(value, dict):
        raise ValueError(f"内置 config.yml 缺少配置分区：{name}")
    return deepcopy(value)


def config_section(name: str) -> dict[str, Any]:
    home = Path(os.environ.get("CAMPFIRE_HOME", "~/.campfire")).expanduser().resolve()
    value = effective_config(home / "config.yml").get(name)
    if not isinstance(value, dict):
        raise ValueError(f"有效 config.yml 缺少配置分区：{name}")
    return deepcopy(value)


def effective_config(user_path: Path) -> dict[str, Any]:
    """Merge optional user overrides onto packaged defaults."""
    config = deepcopy(builtin_config())
    if not user_path.is_file():
        return config
    try:
        override = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"用户 config.yml 不是合法 YAML：{exc}") from exc
    if not isinstance(override, dict):
        raise ValueError("用户 config.yml 必须是 YAML mapping")
    if not isinstance(override.get("version"), int):
        raise ValueError("用户 config.yml 缺少整数 version")
    unknown = sorted(set(override) - set(config))
    if unknown:
        raise ValueError("用户 config.yml 包含未知顶级分区：" + ", ".join(unknown))
    return _deep_merge(config, override)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
