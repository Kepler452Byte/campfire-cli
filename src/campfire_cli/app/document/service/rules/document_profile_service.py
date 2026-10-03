from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.repository.document_profile_repository import (
    DocumentProfileRepository,
)
from campfire_cli.app.document.service.rules.profile_candidates import workspace_candidate_sets
from campfire_cli.app.document.service.rules.profile_registry import ProfileRegistry
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError


class DocumentProfileService:
    def __init__(
        self,
        workspace_id: str,
        vault_root: Path,
        type_config: dict[str, Any],
        repository: DocumentProfileRepository,
    ) -> None:
        self._workspace_id = workspace_id
        self._vault_root = vault_root
        self._type_config = type_config
        self._repository = repository

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
        profiles = self._profiles()
        try:
            profile = profiles.get(name)
        except ConfigurationError as exc:
            if name not in self._type_config.get("types", {}):
                raise
            raise ConfigurationError(
                "show 接收 Profile 名，不是文档类型；请用 resolve 按类型解析",
                code="profile-name-required",
                profile=name,
                hint=(
                    f"campfire --workspace {self._workspace_id} "
                    f"document profile resolve --type {name}"
                ),
            ) from exc
        return {
            "status": "ok",
            "workspace_id": self._workspace_id,
            "profile": profile.model_dump(self._candidate_sets()),
        }

    def resolve(
        self, relative_path: str | None = None, document_type: str | None = None
    ) -> dict[str, Any]:
        if (relative_path is None) == (document_type is None):
            raise ConfigurationError(
                "请选择 --path 解析已有文档，或 --type 解析新建文档契约",
                code="profile-selector-invalid",
            )
        path = None
        frontmatter: dict[str, Any] = {}
        if relative_path is not None:
            path = (self._vault_root / relative_path).resolve()
            if self._vault_root != path and self._vault_root not in path.parents:
                raise ConfigurationError("path 必须位于当前 Workspace 内")
            if not path.is_file():
                raise ConfigurationError(f"文档不存在：{relative_path}")
            frontmatter = parse_document(path.read_text(encoding="utf-8")).frontmatter
            document_type = frontmatter.get("type")
        if not isinstance(document_type, str) or document_type not in self._type_config.get(
            "types", {}
        ):
            raise ConfigurationError(
                "未知文档类型", code="document-type-invalid", actual=document_type
            )
        profile = self._profiles().resolve(document_type, frontmatter, path)
        return {
            "status": "ok",
            "workspace_id": self._workspace_id,
            "path": path.relative_to(self._vault_root).as_posix() if path else None,
            "type": document_type,
            "profile": profile.model_dump(self._candidate_sets()),
        }

    def _profiles(self) -> ProfileRegistry:
        return ProfileRegistry(self._type_config, self._repository.load())

    def _candidate_sets(self) -> dict[str, list[str]]:
        return workspace_candidate_sets(self._vault_root)
