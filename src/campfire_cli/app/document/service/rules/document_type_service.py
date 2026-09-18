from __future__ import annotations

from typing import Any

from campfire_cli.app.document.repository.document_type_repository import (
    DocumentTypeRepository,
)


class DocumentTypeService:
    def __init__(
        self,
        workspace_id: str,
        repository: DocumentTypeRepository,
    ) -> None:
        self._workspace_id = workspace_id
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
