"""Build targeted relationship edits and protect the complete preview plan."""

from __future__ import annotations

from pathlib import Path

from campfire_cli.app.base.schema.operation_schema import maintenance_sync_follow_up
from campfire_cli.app.document.service.index.document_index_service import DocumentIndexService
from campfire_cli.common.documents.domain_context import DomainContextError, resolve_domain_context
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.documents.related_docs import (
    RELATED_DOCS,
    related_documents,
    rewrite_related_docs,
)
from campfire_cli.common.filesystem import FileWrite
from campfire_cli.common.hashing import file_sha256, text_sha256
from campfire_cli.config.settings import WorkspaceSettings


def prepare_document_relocation(
    vault_root: Path,
    source: Path,
    target: Path,
    moved_text: str,
    index: DocumentIndexService,
) -> tuple[list[FileWrite], list[str], dict[Path, str | None]]:
    source_name = source.relative_to(vault_root).as_posix()
    target_name = target.relative_to(vault_root).as_posix()
    references = index.referencing(source_name)
    mapping = {source_name: target_name}
    writes = [FileWrite(target, rewrite_related_docs(moved_text, mapping))]
    expected = {target: None, source: file_sha256(source)}
    changed: list[str] = []
    for name in references:
        if name == source_name:
            continue
        path = vault_root / name
        text = path.read_bytes().decode("utf-8")
        digest = text_sha256(text)
        updated = rewrite_related_docs(text, mapping)
        expected[path] = digest
        if updated != text:
            writes.append(FileWrite(path, updated))
            changed.append(name)
    return writes, changed, expected


def refresh_after_write(index: DocumentIndexService, paths: set[str]) -> list[dict]:
    try:
        index.update_paths(paths)
    except Exception as exc:
        # Files are already committed. Never report a failed rename that callers may replay.
        return [
            {
                "code": "document-index-refresh-failed",
                "write_performed": True,
                "message": str(exc),
                "hint": "文件已写入；修复索引问题后重新查询，不要重复写入。",
            }
        ]
    return []


def relationship_follow_up(settings: WorkspaceSettings, paths: set[str], texts: list[str]):
    for text in texts:
        paths.update(
            item.target
            for item in related_documents(parse_document(text).frontmatter.get(RELATED_DOCS), "")
            if item.target
        )
    scopes: set[str] = set()
    for name in paths:
        path = settings.vault_root / name
        try:
            context = resolve_domain_context(settings.vault_root, path)
            scopes.add(context.root.relative_to(settings.vault_root).as_posix())
        except DomainContextError:
            if not path.exists():
                continue
            for scope in settings.document_types.get("scope_roots", []):
                if name.startswith(scope.rstrip("/") + "/"):
                    scopes.add(scope)
                    break
    return maintenance_sync_follow_up(settings.workspace_id, scopes)
