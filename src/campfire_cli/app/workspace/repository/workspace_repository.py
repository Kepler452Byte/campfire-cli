from __future__ import annotations

import json
from pathlib import Path

from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceRegistry
from campfire_cli.common.filesystem import atomic_write


class FilesystemWorkspaceRepository:
    def __init__(self, governance_root: Path) -> None:
        self._root = governance_root

    def load_registry(self) -> WorkspaceRegistry:
        path = self._root / "registry.json"
        if not path.is_file():
            return WorkspaceRegistry()
        return WorkspaceRegistry.model_validate_json(path.read_text(encoding="utf-8"))

    def save_registry(self, registry: WorkspaceRegistry) -> None:
        atomic_write(
            self._root / "registry.json",
            json.dumps(registry.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        )

    def initialize_configs(
        self, workspace_id: str, configs: dict[str, dict]
    ) -> tuple[list[str], list[str]]:
        config_root = self._root / "workspaces" / workspace_id / "config"
        created: list[str] = []
        preserved: list[str] = []
        for name, payload in configs.items():
            target = config_root / name
            if target.exists():
                preserved.append(str(target))
                continue
            atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            created.append(str(target))
        return created, preserved

    @staticmethod
    def create_scaffold(root: Path, directories: tuple[str, ...]) -> list[str]:
        for relative in directories:
            (root / relative).mkdir(parents=True, exist_ok=True)
        return list(directories)
