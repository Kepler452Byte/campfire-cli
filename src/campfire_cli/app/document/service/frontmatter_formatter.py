"""
SPEC:
  name: frontmatter_formatter
  purpose: 按文档有效 Profile 的字段顺序格式化 Vault frontmatter
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - check 模式只读报告字段顺序异常
    - apply 模式只重排顶级字段块并保留字段值、注释和正文
    - 不属于 Profile 的字段按原相对顺序保留在标准字段之后并交由 Validator 报告
  safety:
    - 不新增、删除或修改字段值
    - frontmatter 缺失、未闭合或存在重复顶级字段时不修改
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import (
    frontmatter_bounds,
    iter_documents,
)
from campfire_cli.common.documents.frontmatter_schema import KEY_RE, parse_shape


def split_blocks(text: str) -> tuple[list[str], list[tuple[str, list[str]]], list[str]]:
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
    return preamble, blocks, lines


def ordered_keys(blocks: list[tuple[str, list[str]]], field_order: list[str]) -> list[str]:
    keys = [key for key, _ in blocks]
    known = [key for key in field_order if key in keys]
    unknown = [key for key in keys if key not in field_order]
    return known + unknown


def format_text(text: str, field_order: list[str]) -> tuple[str, list[str]]:
    bounds = frontmatter_bounds(text)
    if not bounds:
        return text, ["frontmatter-missing-or-unclosed"]
    preamble, blocks, _ = split_blocks(text)
    keys = [key for key, _ in blocks]
    if len(keys) != len(set(keys)):
        return text, ["frontmatter-duplicate-key"]
    by_key = {key: lines for key, lines in blocks}
    sorted_keys = ordered_keys(blocks, field_order)
    rendered_lines = [*preamble]
    for key in sorted_keys:
        rendered_lines.extend(by_key[key])
    rendered = "---\n" + "\n".join(rendered_lines) + text[bounds[1] :]
    return rendered, []


def build_result(
    root: Path, type_config: dict[str, Any], schema: dict[str, Any], apply: bool
) -> dict[str, Any]:
    root = root.resolve()
    profiles = ProfileRegistry(type_config, schema)
    issues: list[dict[str, str]] = []
    changed: list[str] = []
    documents = iter_documents(root, type_config)
    for path in documents:
        original = path.read_text(encoding="utf-8")
        values, _ = parse_shape(original)
        profile = profiles.resolve(values.get("type"), values, path)
        formatted, errors = format_text(original, list(profile.field_order))
        rel = str(path.relative_to(root))
        for error in errors:
            issues.append({"code": error, "path": rel})
        if not errors and formatted != original:
            changed.append(rel)
            if apply:
                path.write_text(formatted, encoding="utf-8")
    return {
        "status": "issues-found" if issues else ("applied" if apply else "ok"),
        "mode": "apply" if apply else "check",
        "document_count": len(documents),
        "reorder_count": len(changed),
        "reordered": changed,
        "issues": issues,
    }
