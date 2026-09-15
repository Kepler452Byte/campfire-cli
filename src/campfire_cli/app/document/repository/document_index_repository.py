"""SQLite persistence for the rebuildable document query projection."""

from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from campfire_cli.app.document.schema import (
    DocumentEdgeRecord,
    DocumentIndexMetadata,
    DocumentIndexRecord,
)
from campfire_cli.common.database.models import Document, DocumentEdge, DocumentIndexState


class SqliteDocumentIndexRepository:
    def __init__(self, session: Session, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def load_documents(self) -> list[DocumentIndexRecord]:
        rows = self._session.scalars(
            select(Document)
            .where(Document.workspace_id == self._workspace_id)
            .order_by(Document.path)
        ).all()
        return [self._document(row) for row in rows]

    def load_edges(self) -> list[DocumentEdgeRecord]:
        rows = self._session.scalars(
            select(DocumentEdge)
            .where(DocumentEdge.workspace_id == self._workspace_id)
            .order_by(DocumentEdge.source_path, DocumentEdge.line, DocumentEdge.raw_target)
        ).all()
        return [self._edge(row) for row in rows]

    def load_state(self) -> DocumentIndexMetadata | None:
        row = self._session.get(DocumentIndexState, self._workspace_id)
        if row is None:
            return None
        return DocumentIndexMetadata(
            schema_version=row.schema_version,
            parser_version=row.parser_version,
            config_hash=row.config_hash,
            topology_hash=row.topology_hash,
            generation=row.generation,
            status=row.status,
            rebuilt_at=row.rebuilt_at,
            indexed_at=row.indexed_at,
        )

    def replace_snapshot(
        self,
        documents: list[DocumentIndexRecord],
        edges: list[DocumentEdgeRecord],
        metadata: DocumentIndexMetadata,
    ) -> None:
        try:
            self._session.execute(
                delete(DocumentEdge).where(DocumentEdge.workspace_id == self._workspace_id)
            )
            self._session.execute(
                delete(Document).where(Document.workspace_id == self._workspace_id)
            )
            self._session.add_all(
                [
                    Document(
                        workspace_id=self._workspace_id,
                        path=item.path,
                        content_hash=item.content_hash,
                        name=item.name,
                        document_type=item.document_type,
                        domain_id=item.domain_id,
                        project_id=item.project_id,
                        status=item.status,
                        lifecycle=item.lifecycle,
                        priority=item.priority,
                        assignee_json=json.dumps(item.assignee, ensure_ascii=False),
                        due=item.due,
                        source_updated=item.source_updated,
                        source_size=item.source_size,
                        source_mtime_ns=item.source_mtime_ns,
                        queryable=item.queryable,
                        exists=True,
                    )
                    for item in documents
                ]
            )
            self._session.add_all(
                [
                    DocumentEdge(
                        workspace_id=self._workspace_id,
                        source_path=item.source_path,
                        target_path=item.target_path,
                        raw_target=item.raw_target,
                        relation_type=item.relation_type,
                        resolution=item.resolution,
                        candidates_json=json.dumps(item.candidates, ensure_ascii=False),
                        line=item.line,
                    )
                    for item in edges
                ]
            )
            row = self._session.get(DocumentIndexState, self._workspace_id)
            if row is None:
                row = DocumentIndexState(workspace_id=self._workspace_id)
                self._session.add(row)
            row.schema_version = metadata.schema_version
            row.parser_version = metadata.parser_version
            row.config_hash = metadata.config_hash
            row.topology_hash = metadata.topology_hash
            row.generation = metadata.generation
            row.status = metadata.status
            row.rebuilt_at = metadata.rebuilt_at
            row.indexed_at = metadata.indexed_at
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    @staticmethod
    def _document(row: Document) -> DocumentIndexRecord:
        return DocumentIndexRecord(
            path=row.path,
            content_hash=row.content_hash,
            name=row.name,
            document_type=row.document_type,
            domain_id=row.domain_id,
            project_id=row.project_id,
            status=row.status,
            lifecycle=row.lifecycle,
            priority=row.priority,
            assignee=json.loads(row.assignee_json or "[]"),
            due=row.due,
            source_updated=row.source_updated,
            source_size=row.source_size or 0,
            source_mtime_ns=row.source_mtime_ns or 0,
            queryable=row.queryable,
            indexed_at=row.indexed_at,
        )

    @staticmethod
    def _edge(row: DocumentEdge) -> DocumentEdgeRecord:
        return DocumentEdgeRecord(
            source_path=row.source_path,
            target_path=row.target_path,
            raw_target=row.raw_target,
            relation_type=row.relation_type,
            resolution=row.resolution,
            candidates=json.loads(row.candidates_json or "[]"),
            line=row.line,
        )
