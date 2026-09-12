"""Shared helpers for layered Vault frontmatter schemas."""

from __future__ import annotations

import re
from pathlib import Path

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
    if path is None:
        return False
    for parent in [path.parent, *path.parents]:
        marker = parent / "_领域.md"
        if marker.is_file():
            marker_values, _ = parse_shape(marker.read_text(encoding="utf-8"))
            return marker_values.get("governance") == "project-docs"
    return False
