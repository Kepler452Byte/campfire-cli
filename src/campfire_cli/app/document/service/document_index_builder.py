"""Build document and relationship records from Workspace source files."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from campfire_cli.app.document.schema import DocumentEdgeRecord, DocumentIndexRecord
from campfire_cli.common.documents.domain_context import DomainContextError, resolve_domain_context
from campfire_cli.common.documents.links import (
    LinkReference,
    extract_link_references,
    resolve_declared_reference,
    resolve_link_reference,
    stem_index,
)
from campfire_cli.common.documents.markdown import MarkdownDocument, parse_document
from campfire_cli.config.settings import WorkspaceSettings

DECLARED_FIELDS = {
    "related": "declared-related",
    "superseded_by": "declared-superseded-by",
}


class DocumentIndexBuilder:
    """Translate current Workspace facts into deterministic index records."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        project_roots: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._project_roots = dict(project_roots or {})
        self.config_hash = self._effective_config_hash()

    def record(self, path: Path, text: str, parsed: MarkdownDocument) -> DocumentIndexRecord:
        frontmatter = parsed.frontmatter
        context = self._domain_context(path)
        stat = path.stat()
        document_type = self._string(frontmatter.get("type"))
        return DocumentIndexRecord(
            path=path.relative_to(self._settings.vault_root).as_posix(),
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            name=self._string(frontmatter.get("name")),
            document_type=document_type,
            domain_id=context[0],
            project_id=self._project_id(path, context),
            status=self._string(frontmatter.get("status")),
            lifecycle=self._string(frontmatter.get("lifecycle")),
            priority=self._string(frontmatter.get("priority")),
            assignee=self._strings(frontmatter.get("assignee")),
            due=self._date_string(frontmatter.get("due")),
            source_updated=self._date_string(frontmatter.get("updated")),
            source_size=stat.st_size,
            source_mtime_ns=stat.st_mtime_ns,
            queryable=document_type != "moc",
        )

    def edges_for_sources(
        self,
        records: dict[str, DocumentIndexRecord],
        paths: dict[str, Path],
        sources: set[str],
        parsed_by_path: dict[str, tuple[str, MarkdownDocument]],
    ) -> list[DocumentEdgeRecord]:
        queryable_paths = {
            paths[relative].resolve()
            for relative, record in records.items()
            if record.queryable and relative in paths
        }
        by_stem = stem_index(queryable_paths)
        edges: list[DocumentEdgeRecord] = []
        for relative in sorted(sources):
            path = paths[relative]
            _text, parsed = parsed_by_path.get(relative) or self._read_document(path)
            edges.extend(self._declared_edges(relative, path, parsed, queryable_paths, by_stem))
            for reference in extract_link_references(parsed.body):
                if self._is_non_document_reference(reference):
                    continue
                resolution = resolve_link_reference(
                    self._settings.vault_root, path, reference, queryable_paths, by_stem
                )
                if resolution.external:
                    continue
                edges.append(
                    self._edge(
                        relative,
                        reference.raw_target,
                        reference.relation_type,
                        resolution.status,
                        resolution.matches,
                        reference.line + parsed.body_start_line - 1,
                    )
                )
        return self._deduplicate_edges(edges)

    def topology_hash(self) -> str:
        marker_names = {
            self._settings.governance.get("space_marker", "_空间.md"),
            self._settings.governance.get("domain_marker", "_领域.md"),
        }
        digest = hashlib.sha256()
        digest.update(
            json.dumps(
                self._project_roots,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\0")
        for path in sorted(
            (
                path
                for name in marker_names
                for path in self._settings.vault_root.rglob(name)
                if path.is_file()
            ),
            key=lambda item: item.relative_to(self._settings.vault_root).as_posix().casefold(),
        ):
            relative = path.relative_to(self._settings.vault_root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def known_scope_ids(self) -> tuple[set[str], set[str]]:
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        domains: set[str] = set()
        for marker in self._settings.vault_root.rglob(marker_name):
            frontmatter = parse_document(marker.read_text(encoding="utf-8")).frontmatter
            domain = self._string(frontmatter.get("domain_id"))
            if domain:
                domains.add(domain)
        return domains, set(self._project_roots.values())

    def _declared_edges(
        self,
        relative: str,
        path: Path,
        parsed: MarkdownDocument,
        candidates: set[Path],
        by_stem: dict[str, tuple[Path, ...]],
    ) -> list[DocumentEdgeRecord]:
        edges: list[DocumentEdgeRecord] = []
        for field, relation_type in DECLARED_FIELDS.items():
            for raw_target in self._strings(parsed.frontmatter.get(field)):
                resolution = resolve_declared_reference(
                    self._settings.vault_root, path, raw_target, candidates, by_stem
                )
                edges.append(
                    self._edge(
                        relative,
                        raw_target,
                        relation_type,
                        resolution.status,
                        resolution.matches,
                        None,
                    )
                )
        return edges

    def _edge(
        self,
        source: str,
        raw_target: str,
        relation_type: str,
        resolution: str,
        matches: tuple[Path, ...],
        line: int | None,
    ) -> DocumentEdgeRecord:
        relative_matches = [
            item.relative_to(self._settings.vault_root).as_posix() for item in matches
        ]
        return DocumentEdgeRecord(
            source_path=source,
            target_path=relative_matches[0] if len(relative_matches) == 1 else None,
            raw_target=raw_target,
            relation_type=relation_type,
            resolution=resolution,
            candidates=relative_matches,
            line=line,
        )

    def _domain_context(self, path: Path) -> tuple[str | None, str | None]:
        try:
            context = resolve_domain_context(
                self._settings.vault_root, path, self._project_roots
            )
            return context.domain_id, context.project_id
        except DomainContextError:
            return None, None

    def _project_id(self, path: Path, context: tuple[str | None, str | None]) -> str | None:
        return context[1]

    def _effective_config_hash(self) -> str:
        payload = {
            "document_types": self._settings.document_types,
            "frontmatter_schema": self._settings.frontmatter_schema,
            "governance": {
                "space_marker": self._settings.governance.get("space_marker"),
                "domain_marker": self._settings.governance.get("domain_marker"),
            },
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _read_document(path: Path) -> tuple[str, MarkdownDocument]:
        text = path.read_text(encoding="utf-8")
        return text, parse_document(text)

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _date_string(value: Any) -> str | None:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item]
        return []

    @staticmethod
    def _is_non_document_reference(reference: LinkReference) -> bool:
        target = reference.raw_target.strip().strip("<>").split("#", 1)[0]
        suffix = Path(target).suffix.lower()
        return bool(suffix and suffix != ".md")

    @staticmethod
    def _deduplicate_edges(edges: list[DocumentEdgeRecord]) -> list[DocumentEdgeRecord]:
        unique: dict[tuple[Any, ...], DocumentEdgeRecord] = {}
        for edge in edges:
            key = (
                edge.source_path,
                edge.target_path,
                edge.raw_target,
                edge.relation_type,
                edge.resolution,
                tuple(edge.candidates),
                edge.line,
            )
            unique.setdefault(key, edge)
        return list(unique.values())
