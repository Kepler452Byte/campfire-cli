from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from yaml import YAMLError

from campfire_cli.common.documents.document_types import frontmatter_bounds


@dataclass(frozen=True)
class MarkdownDocument:
    frontmatter: dict[str, Any]
    body: str
    has_frontmatter: bool
    body_start_line: int = 1


def parse_document(text: str) -> MarkdownDocument:
    bounds = frontmatter_bounds(text)
    if bounds is None:
        return MarkdownDocument({}, text, False)
    start, end = bounds
    raw = text[start:end]
    try:
        value = yaml.safe_load(raw) or {}
    except YAMLError:
        value = _parse_lenient_scalars(raw)
    if not isinstance(value, dict):
        return MarkdownDocument({}, text, False)
    body_start = end + len(text[end:].splitlines(keepends=True)[0])
    body_start += len(text[body_start:].splitlines(keepends=True)[0])
    return MarkdownDocument(
        value,
        text[body_start:],
        True,
        text[:body_start].count("\n") + 1,
    )


def _parse_lenient_scalars(raw: str) -> dict[str, Any]:
    """Recover top-level fields so malformed legacy YAML cannot abort a Vault scan."""
    result: dict[str, Any] = {}
    current_list: str | None = None
    for line in raw.splitlines():
        if line.startswith("  - ") and current_list:
            result[current_list].append(line[4:].strip().strip('"'))
            continue
        current_list = None
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if value == "[]":
            result[key] = []
        elif not value:
            result[key] = []
            current_list = key
        elif value in {"true", "false"}:
            result[key] = value == "true"
        else:
            result[key] = value.strip('"')
    return result


def render_document(frontmatter: dict[str, Any], body: str, field_order: list[str]) -> str:
    known = [key for key in field_order if key in frontmatter]
    unknown = [key for key in frontmatter if key not in field_order]
    ordered = {key: frontmatter[key] for key in [*known, *unknown]}
    header = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False).rstrip()
    return f"---\n{header}\n---\n{body.lstrip()}"
