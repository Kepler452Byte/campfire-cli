from __future__ import annotations

from pathlib import Path

import yaml

from campfire_cli.app.workspace.repository.project_migration import migrate_project_records
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
            raise ConfigurationError(
                f"Manifest 无效：{target}：{exc}；旧 Manifest 请先运行 setup 或 upgrade",
                code="manifest-invalid",
            ) from exc

    def upgrade(self, workspace: Path) -> bool:
        """Migrate a version-one Manifest once without changing stable identities."""
        target = self.path(workspace)
        if not target.is_file():
            return False
        original = target.read_text(encoding="utf-8")
        try:
            payload = yaml.safe_load(original) or {}
            if payload.get("schema_version", 1) != 1:
                return False
            manifest = WorkspaceManifest.model_validate(
                migrate_project_records(payload, portable=True)
            )
        except (yaml.YAMLError, ValueError, TypeError) as exc:
            raise ConfigurationError(
                f"Manifest migration failed: {target}: {exc}", code="manifest-migration-invalid"
            ) from exc
        if target.read_text(encoding="utf-8") != original:
            raise ConfigurationError(
                "Manifest changed; retry setup", code="manifest-concurrent-change"
            )
        self.save(workspace, manifest)
        return True

    def save(self, workspace: Path, manifest: WorkspaceManifest) -> Path:
        target = self.path(workspace)
        atomic_write(target, self.render(manifest))
        return target

    @staticmethod
    def render(manifest: WorkspaceManifest) -> str:
        return "".join(
            [
                "# Managed by Campfire CLI. Use `campfire workspace ...`; do not edit directly.\n",
                yaml.safe_dump(
                    manifest.model_dump(mode="json", exclude_none=True),
                    allow_unicode=True,
                    sort_keys=False,
                ),
            ]
        )
