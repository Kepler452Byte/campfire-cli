from __future__ import annotations

from pathlib import Path

import yaml

from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceManifest
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import atomic_write

MANIFEST_FILENAME = ".campfire.yaml"


class WorkspaceManifestRepository:
    """Read and write the portable Workspace metadata stored with a Vault."""

    def path(self, workspace: Path) -> Path:
        return workspace / MANIFEST_FILENAME

    def load(self, workspace: Path) -> WorkspaceManifest | None:
        target = self.path(workspace)
        if not target.is_file():
            return None
        try:
            payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
            return WorkspaceManifest.model_validate(payload)
        except (yaml.YAMLError, ValueError) as exc:
            raise ConfigurationError(f"Manifest 无效：{target}：{exc}") from exc

    def save(self, workspace: Path, manifest: WorkspaceManifest) -> Path:
        target = self.path(workspace)
        content = yaml.safe_dump(
            manifest.model_dump(mode="json", exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
        )
        atomic_write(target, content)
        return target
