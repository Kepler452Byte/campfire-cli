from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document_profile.repository.document_profile_repository import (
    DocumentProfileRepository,
)
from campfire_cli.common.documents.frontmatter_profile import ProfileRegistry
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import workspace_write_lock


class DocumentProfileService:
    def __init__(
        self,
        workspace_id: str,
        vault_root: Path,
        state_root: Path,
        type_config: dict[str, Any],
        repository: DocumentProfileRepository,
    ) -> None:
        self._workspace_id = workspace_id
        self._vault_root = vault_root
        self._state_root = state_root
        self._type_config = type_config
        self._repository = repository

    def sync(self, confirm: bool = False) -> dict[str, Any]:
        current = self._repository.load()
        target = self._repository.packaged()
        changed = current != target
        if changed and confirm:
            with workspace_write_lock(self._state_root.parents[1]):
                self._repository.save(target)
        return {
            "status": "synced" if changed and confirm else "planned" if changed else "current",
            "workspace_id": self._workspace_id,
            "current_version": current.get("version"),
            "target_version": target.get("version"),
            "write_performed": changed and confirm,
            "operations": ["replace frontmatter-schema.json"] if changed else [],
        }

    def list_profiles(self) -> dict[str, Any]:
        profiles = self._profiles()
        return {
            "status": "ok",
            "workspace_id": self._workspace_id,
            "profiles": [
                {
                    "name": profile.name,
                    "field_count": len(profile.field_order),
                    "required_count": len(profile.required),
                }
                for profile in profiles.list()
            ],
        }

    def show_profile(self, name: str) -> dict[str, Any]:
        return {
            "status": "ok",
            "workspace_id": self._workspace_id,
            "profile": self._profiles().get(name).model_dump(),
        }

    def resolve(self, relative_path: str) -> dict[str, Any]:
        path = (self._vault_root / relative_path).resolve()
        if self._vault_root != path and self._vault_root not in path.parents:
            raise ConfigurationError("path 必须位于当前 Workspace 内")
        if not path.is_file():
            raise ConfigurationError(f"文档不存在：{relative_path}")
        frontmatter = parse_document(path.read_text(encoding="utf-8")).frontmatter
        profile = self._profiles().resolve(frontmatter.get("type"), frontmatter, path)
        return {
            "status": "ok",
            "workspace_id": self._workspace_id,
            "path": path.relative_to(self._vault_root).as_posix(),
            "type": frontmatter.get("type"),
            "profile": profile.model_dump(),
        }

    def _profiles(self) -> ProfileRegistry:
        return ProfileRegistry(self._type_config, self._repository.load())
