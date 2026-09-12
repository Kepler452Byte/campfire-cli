"""Discover documents in the configured managed scope."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.common.documents.document_types import safe_path


def exempt_document(path: Path, config: dict[str, Any]) -> bool:
    """Return whether a Markdown file is owned by another app or explicitly unmanaged."""
    return path.name in set(config.get("exempt_basenames", []))


def iter_documents(root: Path, config: dict[str, Any]) -> list[Path]:
    root = root.resolve()
    ignored = set(config.get("ignored_directories", []))
    documents: set[Path] = set()
    space_marker = config.get("space_marker", "_空间.md")
    spaces = [
        marker.parent.relative_to(root).as_posix() for marker in root.glob(f"*/{space_marker}")
    ]
    if spaces:
        inboxes = [value for value in config.get("scope_roots", []) if value.startswith("_收件箱/")]
        scope_roots = [*spaces, *inboxes]
    else:
        scope_roots = config.get("scope_roots", [])
    for raw_root in scope_roots:
        scope = safe_path(root, raw_root)
        if not scope.exists():
            continue
        for path in scope.rglob("*.md"):
            relative = path.relative_to(root)
            if exempt_document(path, config) or any(part in ignored for part in relative.parts):
                continue
            documents.add(path.resolve())
    return sorted(documents, key=lambda path: str(path.relative_to(root)).casefold())
