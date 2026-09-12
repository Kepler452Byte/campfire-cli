from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.repository.document_type_repository import (
    DocumentTypeRepository,
)
from campfire_cli.common.filesystem import workspace_write_lock


class DocumentTypeService:
    def __init__(
        self,
        workspace_id: str,
        state_root: Path,
        repository: DocumentTypeRepository,
    ) -> None:
        self._workspace_id = workspace_id
        self._state_root = state_root
        self._repository = repository

    def list_types(self) -> dict[str, Any]:
        contract = self._repository.load()
        return {
            "status": "ok",
            "workspace_id": self._workspace_id,
            "types": [
                {"name": name, **definition}
                for name, definition in contract.get("types", {}).items()
            ],
        }

    def sync(self, confirm: bool = False) -> dict[str, Any]:
        current = self._repository.load()
        target = self._merge_contract(current, self._repository.packaged())
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
            "operations": ["merge packaged document types"] if changed else [],
        }

    @staticmethod
    def _merge_contract(current: dict[str, Any], packaged: dict[str, Any]) -> dict[str, Any]:
        """Add or update packaged types without deleting Workspace extensions."""
        target = {**current, "version": packaged.get("version", current.get("version"))}
        target["types"] = {
            **current.get("types", {}),
            **packaged.get("types", {}),
        }
        target["scope_roots"] = list(
            dict.fromkeys(
                [
                    *packaged.get("scope_roots", []),
                    *current.get("scope_roots", []),
                ]
            )
        )
        packaged_types = set(packaged.get("types", {}))
        target["profiles"] = {
            name: list(
                dict.fromkeys(
                    [
                        *packaged.get("profiles", {}).get(name, []),
                        *[
                            item
                            for item in current.get("profiles", {}).get(name, [])
                            if item not in packaged_types
                        ],
                    ]
                )
            )
            for name in {
                *current.get("profiles", {}),
                *packaged.get("profiles", {}),
            }
        }
        legacy_ignored = {"assets", "archive", "generated"}
        custom_ignored = [
            item for item in current.get("ignored_directories", []) if item not in legacy_ignored
        ]
        target["ignored_directories"] = list(
            dict.fromkeys([*packaged.get("ignored_directories", []), *custom_ignored])
        )
        target["exempt_basenames"] = list(
            dict.fromkeys(
                [
                    *packaged.get("exempt_basenames", []),
                    *current.get("exempt_basenames", []),
                ]
            )
        )
        return target
