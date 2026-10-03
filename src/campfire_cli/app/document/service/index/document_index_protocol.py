"""Persistence boundary consumed by the document index application service."""

from __future__ import annotations

from typing import Protocol

from campfire_cli.app.document.schema import (
    DocumentEdgeRecord,
    DocumentIndexMetadata,
    DocumentIndexRecord,
)


class DocumentIndexRepositoryProtocol(Protocol):
    def load_documents(self, paths: set[str] | None = None) -> list[DocumentIndexRecord]: ...

    def load_fingerprints(self) -> list[DocumentIndexRecord]: ...

    def load_edges(
        self, *, source: str | None = None, target: str | None = None
    ) -> list[DocumentEdgeRecord]: ...

    def query_documents(
        self, filters: dict[str, str], limit: int | None = None
    ) -> tuple[list[DocumentIndexRecord], int]: ...

    def counts(self) -> tuple[int, int]: ...

    def mark_dirty(self) -> None: ...

    def apply_delta(
        self,
        documents: list[DocumentIndexRecord],
        edges: list[DocumentEdgeRecord],
        metadata: DocumentIndexMetadata,
        deleted: set[str],
        edge_sources: set[str],
        affected_targets: dict[str, bool],
    ) -> None: ...

    def load_state(self) -> DocumentIndexMetadata | None: ...

    def replace_snapshot(
        self,
        documents: list[DocumentIndexRecord],
        edges: list[DocumentEdgeRecord],
        metadata: DocumentIndexMetadata,
    ) -> None: ...
