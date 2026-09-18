"""Persistence boundary consumed by the document index application service."""

from __future__ import annotations

from typing import Protocol

from campfire_cli.app.document.schema import (
    DocumentEdgeRecord,
    DocumentIndexMetadata,
    DocumentIndexRecord,
)


class DocumentIndexRepositoryProtocol(Protocol):
    def load_documents(self) -> list[DocumentIndexRecord]: ...

    def load_edges(self) -> list[DocumentEdgeRecord]: ...

    def load_state(self) -> DocumentIndexMetadata | None: ...

    def replace_snapshot(
        self,
        documents: list[DocumentIndexRecord],
        edges: list[DocumentEdgeRecord],
        metadata: DocumentIndexMetadata,
    ) -> None: ...
