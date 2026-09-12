"""Persistence for the active Workspace document Profile contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from campfire_cli.common.filesystem import atomic_write
from campfire_cli.config.defaults import default_configs


class DocumentProfileRepository:
    def __init__(self, state_root: Path) -> None:
        self._path = state_root / "config" / "frontmatter-schema.json"

    def load(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    @staticmethod
    def packaged() -> dict[str, Any]:
        return default_configs()["frontmatter-schema.json"]

    def save(self, schema: dict[str, Any]) -> None:
        atomic_write(
            self._path,
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        )
