"""SQLite persistence for the rebuildable document query projection."""

from __future__ import annotations

import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from campfire_cli.app.document.schema import (
    DocumentEdgeRecord,
    DocumentIndexMetadata,
    DocumentIndexRecord,
)
from campfire_cli.common.database.models import Document, DocumentEdge, DocumentIndexState
from campfire_cli.common.exceptions import GovernanceBlockedError


class SqliteDocumentIndexRepository:
    def __init__(self, session: Session, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def load_documents(self, paths: set[str] | None = None) -> list[DocumentIndexRecord]:
        statement = select(Document).where(Document.workspace_id == self._workspace_id)
        if paths is not None:
            statement = statement.where(Document.path.in_(paths))
        rows = self._session.scalars(statement.order_by(Document.path)).all()
        return [self._document(row) for row in rows]

    def load_fingerprints(self) -> list[DocumentIndexRecord]:
        rows = self._session.execute(
            select(
                Document.path,
                Document.content_hash,
                Document.source_size,
                Document.source_mtime_ns,
                Document.queryable,
            ).where(Document.workspace_id == self._workspace_id)
        ).mappings()
        return [DocumentIndexRecord(**row) for row in rows]

    def load_edges(
        self, *, source: str | None = None, target: str | None = None
    ) -> list[DocumentEdgeRecord]:
        statement = select(DocumentEdge).where(DocumentEdge.workspace_id == self._workspace_id)
        if source is not None:
            statement = statement.where(DocumentEdge.source_path == source)
        if target is not None:
            statement = statement.where(DocumentEdge.target_path == target)
        rows = self._session.scalars(
            statement.order_by(DocumentEdge.source_path, DocumentEdge.line, DocumentEdge.raw_target)
        ).all()
        return [self._edge(row) for row in rows]

    def load_state(self) -> DocumentIndexMetadata | None:
        row = self._session.get(DocumentIndexState, self._workspace_id, populate_existing=True)
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

    def query_documents(
        self, filters: dict[str, str], limit: int | None = None
    ) -> tuple[list[DocumentIndexRecord], int]:
        fields = {
            "project": Document.project_id,
            "domain": Document.domain_id,
            "type": Document.document_type,
            "document_status": Document.document_status,
            "task_status": Document.task_status,
        }
        statement = select(Document).where(
            Document.workspace_id == self._workspace_id, Document.queryable.is_(True)
        )
        for field, value in filters.items():
            statement = statement.where(fields[field] == value)
        total = self._session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self._session.scalars(statement.order_by(Document.path).limit(limit)).all()
        return [self._document(row) for row in rows], total

    def counts(self) -> tuple[int, int]:
        return tuple(
            self._session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.workspace_id == self._workspace_id)
            )
            or 0
            for model in (Document, DocumentEdge)
        )

    def mark_dirty(self) -> None:
        self._session.execute(
            update(DocumentIndexState)
            .where(DocumentIndexState.workspace_id == self._workspace_id)
            .values(status="dirty")
        )
        self._session.commit()

    def apply_delta(
        self,
        documents: list[DocumentIndexRecord],
        edges: list[DocumentEdgeRecord],
        metadata: DocumentIndexMetadata,
        deleted: set[str],
        edge_sources: set[str],
        affected_targets: dict[str, bool],
    ) -> None:
        self.replace_snapshot(
            documents,
            edges,
            metadata,
            deleted=deleted,
            edge_sources=edge_sources,
            affected_targets=affected_targets,
        )

    def replace_snapshot(
        self,
        documents: list[DocumentIndexRecord],
        edges: list[DocumentEdgeRecord],
        metadata: DocumentIndexMetadata,
        *,
        deleted: set[str] | None = None,
        edge_sources: set[str] | None = None,
        affected_targets: dict[str, bool] | None = None,
    ) -> None:
        try:
            if metadata.generation > 1:
                advanced = self._session.execute(
                    update(DocumentIndexState)
                    .where(
                        DocumentIndexState.workspace_id == self._workspace_id,
                        DocumentIndexState.generation == metadata.generation - 1,
                    )
                    .values(generation=metadata.generation)
                )
                if advanced.rowcount != 1:
                    raise GovernanceBlockedError("索引已被其他操作更新，请重新查询")
            edge_delete = delete(DocumentEdge).where(
                DocumentEdge.workspace_id == self._workspace_id
            )
            document_delete = delete(Document).where(Document.workspace_id == self._workspace_id)
            if deleted is not None:
                edge_delete = edge_delete.where(
                    DocumentEdge.source_path.in_((edge_sources or set()) | deleted)
                )
                document_delete = document_delete.where(
                    Document.path.in_(deleted | {item.path for item in documents})
                )
            self._session.execute(edge_delete)
            self._session.execute(document_delete)
            for target, exists in (affected_targets or {}).items():
                self._session.execute(
                    update(DocumentEdge)
                    .where(
                        DocumentEdge.workspace_id == self._workspace_id,
                        DocumentEdge.target_path == target,
                        DocumentEdge.resolution.in_(["resolved", "missing"]),
                    )
                    .values(resolution="resolved" if exists else "missing")
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
                        document_status=item.document_status,
                        lifecycle=item.lifecycle,
                        task_status=item.task_status,
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
            document_status=row.document_status,
            lifecycle=row.lifecycle,
            task_status=row.task_status,
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
