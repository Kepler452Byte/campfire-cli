from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from yaml import YAMLError


@dataclass(frozen=True)
class MarkdownDocument:
    frontmatter: dict[str, Any]
    body: str
    has_frontmatter: bool


def parse_document(text: str) -> MarkdownDocument:
    if not text.startswith("---\n"):
        return MarkdownDocument({}, text, False)
    end = text.find("\n---\n", 4)
    if end < 0:
        return MarkdownDocument({}, text, False)
    raw = text[4:end]
    try:
        value = yaml.safe_load(raw) or {}
    except YAMLError:
        value = _parse_lenient_scalars(raw)
    if not isinstance(value, dict):
        return MarkdownDocument({}, text, False)
    return MarkdownDocument(value, text[end + 5 :], True)


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
