"""Discover documents in the configured managed scope."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from campfire_cli.common.documents.document_types import safe_path
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem.skill_packages import in_skill_package


def exempt_document(path: Path, config: dict[str, Any]) -> bool:
    """Return whether a Markdown file is owned by another app or explicitly unmanaged."""
    return path.name in set(config.get("exempt_basenames", []))


def require_document_path(path: Path, skill_roots: tuple[Path, ...]) -> None:
    if in_skill_package(path, skill_roots):
        raise GovernanceBlockedError(
            "技能包文件独立于普通文档治理，请用文件工具处理",
            code="skill-package-unmanaged",
            path=str(path),
        )


def is_system_scope_path(root: Path, path: Path, config: dict[str, Any]) -> bool:
    """Return whether a path belongs to a configured non-Space document root."""
    resolved = path.resolve()
    return any(
        resolved == scope or scope in resolved.parents
        for raw_root in config.get("scope_roots", [])
        for scope in (safe_path(root.resolve(), raw_root),)
    )


def ignored_directory(name: str, config: dict[str, Any]) -> bool:
    """Return whether a directory is outside managed document scopes."""
    managed_system_directories = {
        part
        for raw_root in config.get("scope_roots", [])
        for part in PurePosixPath(raw_root).parts
        if part.startswith("_")
    }
    return name.startswith(".") or (name.startswith("_") and name not in managed_system_directories)


def iter_documents(
    root: Path,
    config: dict[str, Any],
    roots: Iterable[Path] | None = None,
    *,
    skill_roots: tuple[Path, ...] = (),
) -> list[Path]:
    root = root.resolve()
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
        if not scope.is_dir():
            continue
        for directory, children, files in scope.walk():
            if in_skill_package(directory, skill_roots, directory=True):
                children.clear()
                continue
            children[:] = [
                name
                for name in children
                if not ignored_directory(name, config) and not (directory / name).is_junction()
            ]
            for name in files:
                path = directory / name
                if (
                    path.match("*.md")
                    and not exempt_document(path, config)
                    and not path.is_symlink()
                    and path.is_file()
                ):
                    documents.add(path)
    return sorted(documents, key=lambda path: str(path.relative_to(root)).casefold())
