"""Build document and relationship records from Workspace source files."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from campfire_cli.app.document.schema import DocumentEdgeRecord, DocumentIndexRecord
from campfire_cli.common.documents.domain_context import DomainContextError, resolve_domain_context
from campfire_cli.common.documents.markdown import MarkdownDocument, parse_document
from campfire_cli.common.documents.related_docs import RELATED_DOCS, related_documents
from campfire_cli.config.settings import WorkspaceSettings


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
            document_status=self._string(frontmatter.get("document_status")),
            lifecycle=self._string(frontmatter.get("lifecycle")),
            task_status=self._string(frontmatter.get("task_status")),
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
        candidates = {name for name, record in records.items() if record.queryable}
        edges: list[DocumentEdgeRecord] = []
        for relative in sorted(sources):
            _text, parsed = parsed_by_path.get(relative) or self._read_document(paths[relative])
            for item in related_documents(
                parsed.frontmatter.get(RELATED_DOCS), relative, candidates
            ):
                if item.resolution == "duplicate":
                    continue
                edges.append(
                    DocumentEdgeRecord(
                        source_path=relative,
                        target_path=item.target,
                        raw_target=item.raw,
                        relation_type="related_docs",
                        resolution=item.resolution,
                    )
                )
        return edges

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

    def _domain_context(self, path: Path) -> tuple[str | None, str | None]:
        try:
            context = resolve_domain_context(self._settings.vault_root, path, self._project_roots)
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
