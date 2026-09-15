"""Build and query the device-local projection derived from Markdown documents."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from campfire_cli.app.document.schema import (
    DocumentEdgeRecord,
    DocumentIndexMetadata,
    DocumentIndexRecord,
    DocumentIndexResult,
    DocumentListItem,
    DocumentListResult,
)
from campfire_cli.app.document.service.document_index_builder import DocumentIndexBuilder
from campfire_cli.app.document.service.document_index_protocol import (
    DocumentIndexRepositoryProtocol,
)
from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.common.documents.markdown import MarkdownDocument, parse_document
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.config.settings import WorkspaceSettings

INDEX_SCHEMA_VERSION = 1
PARSER_VERSION = "1"


class DocumentIndexService:
    """Maintain and query a rebuildable SQLite projection of Markdown facts."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        repository: DocumentIndexRepositoryProtocol,
        project_domains: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._builder = DocumentIndexBuilder(settings, project_domains)

    def rebuild(self) -> DocumentIndexResult:
        return self._reconcile(force=True)

    def reconcile(self) -> DocumentIndexResult:
        return self._reconcile(force=False)

    def list_documents(
        self,
        *,
        project: str | None = None,
        domain: str | None = None,
        document_type: str | None = None,
        lifecycle: str | None = None,
    ) -> DocumentListResult:
        index = self.reconcile()
        self._validate_filters(project, domain, document_type, lifecycle)
        filters = {
            key: value
            for key, value in {
                "project": project,
                "domain": domain,
                "type": document_type,
                "lifecycle": lifecycle,
            }.items()
            if value is not None
        }
        records = [item for item in self._repository.load_documents() if item.queryable]
        if project is not None:
            records = [item for item in records if item.project_id == project]
        if domain is not None:
            records = [item for item in records if item.domain_id == domain]
        if document_type is not None:
            records = [item for item in records if item.document_type == document_type]
        if lifecycle is not None:
            records = [item for item in records if item.lifecycle == lifecycle]
        items = [self._list_item(item) for item in sorted(records, key=self._record_sort_key)]
        return DocumentListResult(
            workspace_id=self._settings.workspace_id,
            index_generation=index.generation,
            filters=filters,
            count=len(items),
            items=items,
        )

    def relations(self, relative_path: str) -> tuple[int, dict[str, list[dict[str, Any]]]]:
        index = self.reconcile()
        documents = {item.path: item for item in self._repository.load_documents()}
        if relative_path not in documents:
            raise ConfigurationError(f"文档未进入当前索引：{relative_path}")
        edges = self._repository.load_edges()
        declared: list[dict[str, Any]] = []
        outgoing: list[dict[str, Any]] = []
        incoming: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for edge in edges:
            if edge.source_path == relative_path:
                if edge.resolution != "resolved":
                    unresolved.append(self._unresolved_item(edge))
                elif edge.relation_type.startswith("declared-"):
                    declared.append(self._outgoing_item(edge, documents))
                else:
                    outgoing.append(self._outgoing_item(edge, documents))
            if edge.target_path == relative_path and edge.resolution == "resolved":
                incoming.append(self._incoming_item(edge, documents))
        return index.generation, {
            "declared": declared,
            "outgoing": outgoing,
            "incoming": incoming,
            "unresolved": unresolved,
        }

    def _reconcile(self, *, force: bool) -> DocumentIndexResult:
        paths = iter_documents(self._settings.vault_root, self._settings.document_types)
        paths_by_relative = {
            path.relative_to(self._settings.vault_root).as_posix(): path for path in paths
        }
        existing = {item.path: item for item in self._repository.load_documents()}
        state = self._repository.load_state()
        topology_hash = self._builder.topology_hash()
        full = force or not self._state_is_current(state, topology_hash)
        changed = (
            set(paths_by_relative) if full else self._changed_paths(paths_by_relative, existing)
        )
        deleted = set(existing) - set(paths_by_relative)
        if not changed and not deleted and state is not None:
            return DocumentIndexResult(
                workspace_id=self._settings.workspace_id,
                generation=state.generation,
                document_count=len(existing),
                edge_count=len(self._repository.load_edges()),
                changed_document_count=0,
                full_rebuild=False,
            )

        records = {} if full else dict(existing)
        parsed_by_path: dict[str, tuple[str, MarkdownDocument]] = {}
        for relative in sorted(changed):
            path = paths_by_relative[relative]
            text = path.read_text(encoding="utf-8")
            parsed = parse_document(text)
            parsed_by_path[relative] = (text, parsed)
            records[relative] = self._builder.record(path, text, parsed)
        for relative in deleted:
            records.pop(relative, None)

        queryable_set_changed = any(
            relative in existing and existing[relative].queryable != records[relative].queryable
            for relative in changed
        )
        path_shape_changed = (
            full
            or bool(deleted)
            or queryable_set_changed
            or any(item not in existing for item in changed)
        )
        old_edges = [] if full else self._repository.load_edges()
        if path_shape_changed:
            edge_sources = {path for path, item in records.items() if item.queryable}
            retained_edges: list[DocumentEdgeRecord] = []
        else:
            edge_sources = {path for path in changed if records[path].queryable}
            retained_edges = [edge for edge in old_edges if edge.source_path not in changed]
        edges = [
            *retained_edges,
            *self._builder.edges_for_sources(
                records, paths_by_relative, edge_sources, parsed_by_path
            ),
        ]
        generation = (state.generation if state else 0) + 1
        now = datetime.now(UTC).replace(tzinfo=None)
        metadata = DocumentIndexMetadata(
            schema_version=INDEX_SCHEMA_VERSION,
            parser_version=PARSER_VERSION,
            config_hash=self._builder.config_hash,
            topology_hash=topology_hash,
            generation=generation,
            status="ready",
            rebuilt_at=now if full else state.rebuilt_at if state else now,
            indexed_at=now,
        )
        ordered_records = sorted(records.values(), key=self._record_sort_key)
        ordered_edges = sorted(edges, key=self._edge_sort_key)
        self._repository.replace_snapshot(ordered_records, ordered_edges, metadata)
        return DocumentIndexResult(
            workspace_id=self._settings.workspace_id,
            generation=generation,
            document_count=len(ordered_records),
            edge_count=len(ordered_edges),
            changed_document_count=len(changed) + len(deleted),
            full_rebuild=full,
        )

    def _changed_paths(
        self,
        paths: dict[str, Path],
        existing: dict[str, DocumentIndexRecord],
    ) -> set[str]:
        changed: set[str] = set()
        for relative, path in paths.items():
            current = path.stat()
            previous = existing.get(relative)
            if (
                previous is None
                or previous.source_size != current.st_size
                or previous.source_mtime_ns != current.st_mtime_ns
            ):
                changed.add(relative)
        return changed

    def _state_is_current(self, state: DocumentIndexMetadata | None, topology_hash: str) -> bool:
        return bool(
            state
            and state.status == "ready"
            and state.schema_version == INDEX_SCHEMA_VERSION
            and state.parser_version == PARSER_VERSION
            and state.config_hash == self._builder.config_hash
            and state.topology_hash == topology_hash
        )

    def _validate_filters(
        self,
        project: str | None,
        domain: str | None,
        document_type: str | None,
        lifecycle: str | None,
    ) -> None:
        known_domains, known_projects = self._builder.known_scope_ids()
        if project is not None and project not in known_projects:
            raise ConfigurationError(f"未知 Project：{project}")
        if domain is not None and domain not in known_domains:
            raise ConfigurationError(f"未知 Domain：{domain}")
        if (
            document_type is not None
            and document_type not in self._settings.document_types["types"]
        ):
            raise ConfigurationError(f"未知文档类型：{document_type}")
        if lifecycle is None:
            return
        allowed = {
            value
            for profile in self._settings.frontmatter_schema["profiles"].values()
            for value in profile.get("enums", {}).get("lifecycle", [])
        }
        if lifecycle not in allowed:
            raise ConfigurationError(f"未知文档 lifecycle：{lifecycle}；allowed={sorted(allowed)}")

    @staticmethod
    def _record_sort_key(item: DocumentIndexRecord) -> str:
        return item.path.casefold()

    @staticmethod
    def _edge_sort_key(item: DocumentEdgeRecord) -> tuple[str, str, str, int]:
        return (
            item.source_path.casefold(),
            item.relation_type,
            item.raw_target.casefold(),
            item.line or 0,
        )

    @staticmethod
    def _list_item(item: DocumentIndexRecord) -> DocumentListItem:
        return DocumentListItem(
            path=item.path,
            name=item.name,
            type=item.document_type,
            project=item.project_id,
            domain=item.domain_id,
            status=item.status,
            lifecycle=item.lifecycle,
            priority=item.priority,
            assignee=item.assignee,
            due=item.due,
            updated=item.source_updated,
        )

    @staticmethod
    def _outgoing_item(
        edge: DocumentEdgeRecord, documents: dict[str, DocumentIndexRecord]
    ) -> dict[str, Any]:
        target = documents[edge.target_path or ""]
        return {
            "target": target.path,
            "name": target.name,
            "type": target.document_type,
            "project": target.project_id,
            "domain": target.domain_id,
            "relation_type": edge.relation_type,
            "raw_target": edge.raw_target,
            "line": edge.line,
        }

    @staticmethod
    def _incoming_item(
        edge: DocumentEdgeRecord, documents: dict[str, DocumentIndexRecord]
    ) -> dict[str, Any]:
        source = documents[edge.source_path]
        return {
            "source": source.path,
            "name": source.name,
            "type": source.document_type,
            "project": source.project_id,
            "domain": source.domain_id,
            "relation_type": edge.relation_type,
            "raw_target": edge.raw_target,
            "line": edge.line,
        }

    @staticmethod
    def _unresolved_item(edge: DocumentEdgeRecord) -> dict[str, Any]:
        return {
            "raw_target": edge.raw_target,
            "relation_type": edge.relation_type,
            "resolution": edge.resolution,
            "candidates": edge.candidates,
            "line": edge.line,
        }
