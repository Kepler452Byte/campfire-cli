"""Discover documents in the configured managed scope."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from campfire_cli.common.documents.document_types import safe_path


def exempt_document(path: Path, config: dict[str, Any]) -> bool:
    """Return whether a Markdown file is owned by another app or explicitly unmanaged."""
    return path.name in set(config.get("exempt_basenames", []))


def is_system_scope_path(root: Path, path: Path, config: dict[str, Any]) -> bool:
    """Return whether a path belongs to a configured non-Space document root."""
    resolved = path.resolve()
    return any(
        resolved == scope or scope in resolved.parents
        for raw_root in config.get("scope_roots", [])
        for scope in (safe_path(root.resolve(), raw_root),)
    )


def iter_documents(
    root: Path,
    config: dict[str, Any],
    roots: Iterable[Path] | None = None,
) -> list[Path]:
    root = root.resolve()
    ignored = set(config.get("ignored_directories", []))
    documents: set[Path] = set()
    space_marker = config.get("space_marker", "_空间.md")
    if roots is not None:
        scope_paths = [path.resolve() for path in roots]
    else:
        spaces = [
            marker.parent.relative_to(root).as_posix() for marker in root.glob(f"*/{space_marker}")
        ]
        if spaces:
            scope_roots = [*spaces, *config.get("scope_roots", [])]
        else:
            scope_roots = config.get("scope_roots", [])
        scope_paths = [safe_path(root, raw_root) for raw_root in scope_roots]
    for scope in scope_paths:
        if scope != root and root not in scope.parents:
            continue
        if not scope.exists():
            continue
        for path in scope.rglob("*.md"):
            relative = path.relative_to(root)
            if exempt_document(path, config) or any(part in ignored for part in relative.parts):
                continue
            if not path.is_file() or any(
                part.is_symlink() for part in (path, *path.parents) if part != root
            ):
                continue
            documents.add(path)
    return sorted(documents, key=lambda path: str(path.relative_to(root)).casefold())
