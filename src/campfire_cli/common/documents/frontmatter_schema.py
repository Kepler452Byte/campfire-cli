"""Shared helpers for layered Vault frontmatter schemas."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from campfire_cli.common.documents.document_types import frontmatter_bounds

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_shape(text: str) -> tuple[dict[str, str], dict[str, str]]:
    bounds = frontmatter_bounds(text)
    if not bounds:
        return {}, {}
    lines = text[bounds[0] : bounds[1]].splitlines()
    values: dict[str, str] = {}
    kinds: dict[str, str] = {}
    current: str | None = None
    for line in lines:
        match = KEY_RE.match(line)
        if match:
            current = match.group(1)
            value = (match.group(2) or "").strip().strip('"').strip("'")
            values[current] = value
            kinds[current] = "list" if value.startswith("[") else "scalar"
        elif current and re.match(r"^\s+-\s+", line):
            kinds[current] = "list"
    return values, kinds


def is_project_context(path: Path | None) -> bool:
    """Return whether a path belongs to a Project root declared by the Manifest.

    A Domain's ``governance`` label and a document's legacy ``project`` field
    are descriptive metadata, not the Project--Domain binding.  The Manifest
    owns that binding through ``projects[].document_domain_id``.
    """
    if path is None:
        return False
    domains: list[str] = []
    for parent in [path.parent, *path.parents]:
        marker = parent / "_领域.md"
        if marker.is_file():
            marker_values, _ = parse_shape(marker.read_text(encoding="utf-8"))
            domain_id = marker_values.get("domain_id")
            if domain_id:
                domains.append(domain_id)
        manifest_path = parent / ".campfire.yaml"
        if manifest_path.is_file():
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            roots = {
                item.get("document_domain_id")
                for item in manifest.get("projects", [])
                if isinstance(item, dict)
            }
            return any(domain in roots for domain in domains)
    return False
