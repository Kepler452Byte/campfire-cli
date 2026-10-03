"""Document persistence adapters."""

from campfire_cli.app.document.repository.document_index_repository import (
    SqliteDocumentIndexRepository,
)

__all__ = ["SqliteDocumentIndexRepository"]
