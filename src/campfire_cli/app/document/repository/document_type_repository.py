"""Persistence for the active Workspace document type contract."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from campfire_cli.config.defaults import effective_config


class DocumentTypeRepository:
    def __init__(self, state_root: Path) -> None:
        self._path = state_root.parents[1] / "config.yml"

    def load(self) -> dict[str, Any]:
        return deepcopy(effective_config(self._path)["document_types"])
