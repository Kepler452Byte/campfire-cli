"""Parse and rewrite the sole managed document relationship field."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

from campfire_cli.common.documents.document_types import frontmatter_bounds
from campfire_cli.common.documents.markdown import parse_document

RELATED_DOCS = "related_docs"


@dataclass(frozen=True)
class RelatedDocument:
    raw: str
    target: str | None
    resolution: str


def related_documents(
    value: Any, source: str, candidates: set[str] | None = None
) -> list[RelatedDocument]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    seen: set[str] = set()
    result: list[RelatedDocument] = []
    for item in values:
        raw = item if isinstance(item, str) else repr(item)
        target = (
            item[2:-2]
            if isinstance(item, str) and item.startswith("[[") and item.endswith("]]")
            else None
        )
        valid = bool(
            isinstance(value, list)
            and target
            and target.endswith(".md")
            and not any(char in target for char in "\\:#|[]\n\r")
            and not target.startswith("/")
            and all(part not in {"", ".", ".."} for part in target.split("/"))
            and PurePosixPath(target).as_posix() == target
        )
        if not valid:
            result.append(RelatedDocument(raw, None, "invalid"))
            continue
        if target == source:
            status = "self"
        elif target in seen:
            status = "duplicate"
        elif candidates is not None and target not in candidates:
            status = "missing"
        else:
            status = "resolved"
        seen.add(target)
        result.append(RelatedDocument(raw, target, status))
    return result


def relation_issues(value: Any, source: str, candidates: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "code": f"related-docs-{item.resolution}",
            "path": source,
            "field": RELATED_DOCS,
            "detail": item.raw,
            "expected_type": "list",
            "example": ["[[mywork/project/记录-example.md]]"],
        }
        for item in related_documents(value, source, candidates)
        if item.resolution != "resolved"
    ]


def rewrite_related_docs(text: str, mapping: dict[str, str]) -> str:
    """Replace exact targets in Frontmatter without changing any body bytes."""
    parsed = parse_document(text)
    values = parsed.frontmatter.get(RELATED_DOCS)
    if not isinstance(values, list):
        return text
    updated = [
        f"[[{mapping[item.target]}]]" if item.target in mapping else original
        for original, item in zip(values, related_documents(values, ""), strict=True)
    ]
    if updated == values:
        return text
    bounds = frontmatter_bounds(text)
    if bounds is None:
        return text
    start, end = bounds
    header = text[start:end]
    pattern = re.compile(r"^related_docs:.*(?:\n(?!(?:[^\s#][^\n:]*:|#))[^\n]*)*", re.MULTILINE)
    replacement = yaml.safe_dump(
        {RELATED_DOCS: updated}, allow_unicode=True, sort_keys=False
    ).rstrip()
    # Restrict replacement to this top-level property, preserving the surrounding header.
    match = pattern.search(header)
    if match is None:
        raise ValueError("related_docs must be a top-level YAML property")
    if text.startswith("---\r\n"):
        replacement = replacement.replace("\n", "\r\n")
    return text[:start] + header[: match.start()] + replacement + header[match.end() :] + text[end:]
