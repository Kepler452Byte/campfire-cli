"""Build and query the device-local projection derived from Markdown documents."""

from __future__ import annotations

import hashlib
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
from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.app.document.service.index.document_index_builder import DocumentIndexBuilder
from campfire_cli.app.document.service.index.document_index_protocol import (
    DocumentIndexRepositoryProtocol,
)
from campfire_cli.app.document.service.rules.profile_registry import ProfileRegistry
from campfire_cli.common.documents.markdown import MarkdownDocument, parse_document
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.config.settings import WorkspaceSettings

INDEX_SCHEMA_VERSION = 2
PARSER_VERSION = "3"


class DocumentIndexService:
    """Maintain and query a rebuildable SQLite projection of Markdown facts."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        repository: DocumentIndexRepositoryProtocol,
        project_roots: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._builder = DocumentIndexBuilder(settings, project_roots)
        self._profiles = ProfileRegistry(settings.document_types, settings.frontmatter_schema)

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
        document_status: str | None = None,
        task_status: str | None = None,
        limit: int | None = None,
    ) -> DocumentListResult:
        index = self.reconcile()
        self._validate_filters(project, domain, document_type, document_status, task_status)
        filters = {
            key: value
            for key, value in {
                "project": project,
                "domain": domain,
                "type": document_type,
                "document_status": document_status,
                "task_status": task_status,
            }.items()
            if value is not None
        }
        records, total = self._repository.query_documents(filters, limit)
        items = [self._list_item(item) for item in records]
        return DocumentListResult(
            workspace_id=self._settings.workspace_id,
            index_generation=index.generation,
            filters=filters,
            count=len(items),
            total=total,
            returned=len(items),
            truncated=len(items) < total,
            items=items,
        )

    def relations(self, relative_path: str) -> tuple[int, dict[str, Any]]:
        index = self.reconcile()
        edges = [
            *self._repository.load_edges(source=relative_path),
            *self._repository.load_edges(target=relative_path),
        ]
        documents = {
            item.path: item
            for item in self._repository.load_documents(
                {
                    relative_path,
                    *(e.source_path for e in edges),
                    *(e.target_path for e in edges if e.target_path),
                }
            )
        }
        if relative_path not in documents:
            raise ConfigurationError(f"文档未进入当前索引：{relative_path}")
        edges = list({(e.source_path, e.raw_target, e.resolution): e for e in edges}.values())
        outgoing: list[dict[str, Any]] = []
        incoming: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for edge in edges:
            if edge.source_path == relative_path:
                if edge.resolution != "resolved":
                    unresolved.append(self._unresolved_item(edge))
                else:
                    outgoing.append(self._outgoing_item(edge, documents))
            if edge.target_path == relative_path and edge.resolution == "resolved":
                incoming.append(self._incoming_item(edge, documents))
        return index.generation, {
            "outgoing": outgoing,
            "incoming": incoming,
            "unresolved": unresolved,
            "out_degree": len(outgoing),
            "in_degree": len(incoming),
        }

    def relation_views(self, sources: list[Path]) -> dict[Path, list[dict[str, Any]]]:
        self.reconcile()
        records = {r.path: r for r in self._repository.load_documents() if r.queryable}
        results = {path: [] for path in sources}
        by_name = {p.relative_to(self._settings.vault_root).as_posix(): p for p in sources}
        for edge in self._repository.load_edges():
            if edge.resolution != "resolved":
                continue
            for source, target, kind in (
                (edge.source_path, edge.target_path, "direct-link"),
                (edge.target_path, edge.source_path, "backlink"),
            ):
                if source not in by_name or target not in records:
                    continue
                record = records[target]
                results[by_name[source]].append(
                    {
                        "target": target.removesuffix(".md"),
                        "target_name": record.name or Path(target).stem,
                        "target_domain": record.domain_id or "",
                        "type": kind,
                        "score": 1.0,
                        "reasons": ["related_docs 显式关联"],
                    }
                )
        for items in results.values():
            items.sort(key=lambda item: (item["type"], item["target"]))
        return results

    def referencing(self, relative_path: str) -> list[str]:
        self.reconcile()
        return sorted(
            {
                edge.source_path
                for edge in self._repository.load_edges(target=relative_path)
                if edge.resolution == "resolved"
            }
        )

    def update_paths(self, paths: set[str]) -> DocumentIndexResult:
        return self._reconcile(force=False, known_changes=paths)

    def generation(self) -> int:
        state = self._repository.load_state()
        return state.generation if state else 0

    def prepare_write(self, generation: int) -> None:
        """Recheck the indexed file set under the caller's write lock."""
        paths = {
            p.relative_to(self._settings.vault_root).as_posix(): p
            for p in iter_documents(self._settings.vault_root, self._settings.document_types)
        }
        existing = {r.path: r for r in self._repository.load_fingerprints()}
        state = self._repository.load_state()
        if (
            state is None
            or state.generation != generation
            or set(paths) != set(existing)
            or self._changed_paths(paths, existing)
            or not self._state_is_current(state, self._builder.topology_hash())
        ):
            raise GovernanceBlockedError("索引或引用范围已变化，请重新预览")
        self._repository.mark_dirty()

    def _reconcile(
        self, *, force: bool, known_changes: set[str] | None = None
    ) -> DocumentIndexResult:
        paths = iter_documents(self._settings.vault_root, self._settings.document_types)
        paths_by_relative = {
            path.relative_to(self._settings.vault_root).as_posix(): path for path in paths
        }
        existing = {item.path: item for item in self._repository.load_fingerprints()}
        state = self._repository.load_state()
        topology_hash = self._builder.topology_hash()
        full = force or not self._state_is_current(state, topology_hash, known_changes is not None)
        changed = (
            set(paths_by_relative) if full else self._changed_paths(paths_by_relative, existing)
        )
        changed |= (known_changes or set()) & set(paths_by_relative)
        deleted = set(existing) - set(paths_by_relative)
        if not full and not changed and not deleted and state is not None:
            return DocumentIndexResult(
                workspace_id=self._settings.workspace_id,
                generation=state.generation,
                document_count=len(existing),
                edge_count=self._repository.counts()[1],
                changed_document_count=0,
                full_rebuild=False,
            )

        records = {} if full else dict(existing)
        parsed_by_path: dict[str, tuple[str, MarkdownDocument]] = {}
        edge_sources: set[str] = set()
        for relative in sorted(changed):
            path = paths_by_relative[relative]
            before = path.stat()
            text = path.read_text(encoding="utf-8")
            stat = path.stat()
            if (before.st_mtime_ns, before.st_size) != (stat.st_mtime_ns, stat.st_size):
                raise GovernanceBlockedError(f"索引读取期间文档发生变化：{relative}")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if not full and relative in existing and digest == existing[relative].content_hash:
                records[relative] = self._repository.load_documents({relative})[0].model_copy(
                    update={"source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns}
                )
                continue
            parsed = parse_document(text)
            parsed_by_path[relative] = (text, parsed)
            records[relative] = self._builder.record(path, text, parsed)
            edge_sources.add(relative)
        for relative in deleted:
            records.pop(relative, None)

        edges = self._builder.edges_for_sources(
            records,
            paths_by_relative,
            {p for p in edge_sources if records[p].queryable},
            parsed_by_path,
        )
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
        if full:
            self._repository.replace_snapshot(list(records.values()), edges, metadata)
        else:
            self._repository.apply_delta(
                [records[p] for p in changed],
                edges,
                metadata,
                deleted,
                edge_sources,
                {p: p in records and records[p].queryable for p in changed | deleted},
            )
        document_count, edge_count = self._repository.counts()
        return DocumentIndexResult(
            workspace_id=self._settings.workspace_id,
            generation=generation,
            document_count=document_count,
            edge_count=edge_count,
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

    def _state_is_current(
        self,
        state: DocumentIndexMetadata | None,
        topology_hash: str,
        completing_write: bool = False,
    ) -> bool:
        return bool(
            state
            and (state.status == "ready" or completing_write)
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
        document_status: str | None,
        task_status: str | None,
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
        if document_status is not None:
            allowed = self._profiles.get("base").field("document_status").values
            if document_status not in allowed:
                raise ConfigurationError(
                    f"未知文档 document_status：{document_status}；allowed={sorted(allowed)}"
                )
        if task_status is not None:
            allowed = self._profiles.get("task").field("task_status").values
            if task_status not in allowed:
                raise ConfigurationError(
                    f"未知任务 task_status：{task_status}；allowed={sorted(allowed)}"
                )

    @staticmethod
    def _list_item(item: DocumentIndexRecord) -> DocumentListItem:
        return DocumentListItem(
            path=item.path,
            name=item.name,
            type=item.document_type,
            project=item.project_id,
            domain=item.domain_id,
            document_status=item.document_status,
            lifecycle=item.lifecycle,
            task_status=item.task_status,
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
