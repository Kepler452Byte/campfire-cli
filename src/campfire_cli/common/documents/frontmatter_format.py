from __future__ import annotations

from typing import Any

import yaml

from campfire_cli.common.documents.document_types import frontmatter_bounds
from campfire_cli.common.documents.frontmatter_schema import KEY_RE


def split_blocks(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    bounds = frontmatter_bounds(text)
    if not bounds:
        raise ValueError("frontmatter missing or unclosed")
    lines = text[bounds[0] : bounds[1]].splitlines()
    preamble: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    current_key: str | None = None
    current_lines: list[str] = []
    for line in lines:
        match = KEY_RE.match(line)
        if match:
            if current_key is not None:
                blocks.append((current_key, current_lines))
            current_key = match.group(1)
            current_lines = [line]
        elif current_key is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    if current_key is not None:
        blocks.append((current_key, current_lines))
    return preamble, blocks


def ordered_keys(blocks: list[tuple[str, list[str]]], field_order: list[str]) -> list[str]:
    keys = [key for key, _ in blocks]
    known = [key for key in field_order if key in keys]
    unknown = [key for key in keys if key not in field_order]
    return known + unknown


def format_text(text: str, field_order: list[str]) -> tuple[str, list[str]]:
    bounds = frontmatter_bounds(text)
    if not bounds:
        return text, ["frontmatter-missing-or-unclosed"]
    preamble, blocks = split_blocks(text)
    keys = [key for key, _ in blocks]
    if len(keys) != len(set(keys)):
        return text, ["frontmatter-duplicate-key"]
    return _render_blocks(preamble, blocks, field_order, text[bounds[1] :]), []


def render_patch(
    text: str,
    values: dict[str, Any],
    body: str,
    field_order: list[str],
    removed_fields: tuple[str, ...] = (),
) -> tuple[str, list[str]]:
    """Patch selected fields while preserving every untouched YAML block verbatim."""
    bounds = frontmatter_bounds(text)
    if not bounds:
        return text, ["frontmatter-missing-or-unclosed"]
    preamble, blocks = split_blocks(text)
    keys = [key for key, _ in blocks]
    if len(keys) != len(set(keys)):
        return text, ["frontmatter-duplicate-key"]
    patched = dict(blocks)
    for key in removed_fields:
        patched.pop(key, None)
    for key, value in values.items():
        patched[key] = (
            yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False).rstrip().splitlines()
        )
    closing_and_body = "\n---\n" + body
    return _render_blocks(preamble, list(patched.items()), field_order, closing_and_body), []


def _render_blocks(
    preamble: list[str],
    blocks: list[tuple[str, list[str]]],
    field_order: list[str],
    suffix: str,
) -> str:
    by_key = dict(blocks)
    rendered_lines = [*preamble]
    for key in ordered_keys(blocks, field_order):
        rendered_lines.extend(by_key[key])
    return "---\n" + "\n".join(rendered_lines) + suffix
