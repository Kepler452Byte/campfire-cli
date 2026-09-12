from __future__ import annotations

import json
from copy import deepcopy
from functools import cache
from importlib.resources import files
from typing import Any

DEFAULT_CONFIG_NAMES = (
    "governance.json",
    "document-types.json",
    "frontmatter-schema.json",
    "skills.json",
    "bases.json",
)


@cache
def builtin_config(name: str) -> dict[str, Any]:
    """Load one immutable product default from the packaged JSON SSOT."""
    resource = files("campfire_cli.resources.defaults").joinpath(name)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("version"), int):
        raise ValueError(f"内置配置缺少整数 version：{name}")
    return value


def default_configs() -> dict[str, dict[str, Any]]:
    """Return independent copies of configs used to initialize a Workspace."""
    return {name: deepcopy(builtin_config(name)) for name in DEFAULT_CONFIG_NAMES}
