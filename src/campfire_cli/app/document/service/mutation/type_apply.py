"""
SPEC:
  name: type_apply
  purpose: 执行已审批的 Vault 文档单选 type 与文件名前缀治理计划
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 仅执行 approved true 的计划项
    - 补齐单选 type 并在原目录内按契约改名
    - 更新唯一文件名 wikilink、明确路径 Markdown 链接和 Canvas 文件节点
  safety:
    - 执行前完整预检，存在任一阻塞问题时不写入
    - 不覆盖目标文件，不跨目录移动，不删除文档正文
    - 不执行缺少 proposed_type 或低置信度未审批项
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from campfire_cli.common.documents.document_types import (
    prefixed_name,
    safe_path,
    set_frontmatter_scalar,
)

WIKILINK_RE = re.compile(r"(!?\[\[)([^\]|#]+)([^\]]*\]\])")
MARKDOWN_LINK_RE = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def preflight(
    root: Path, plan: dict[str, Any], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    approved = [item for item in plan.get("items", []) if item.get("approved") is True]
    issues: list[dict[str, str]] = []
    seen_targets: set[Path] = set()
    operations: list[dict[str, Any]] = []
    for item in approved:
        source_name = item.get("source", "")
        target_name = item.get("target", "")
        doc_type = item.get("proposed_type")
        if not source_name or not target_name:
            issues.append(
                {
                    "code": "type-plan-path-missing",
                    "path": source_name or target_name or "<unknown>",
                }
            )
            continue
        try:
            source = safe_path(root, source_name)
            target = safe_path(root, target_name)
        except ValueError:
            issues.append({"code": "type-plan-path-outside-root", "path": source_name})
            continue
        if not source.is_file():
            issues.append({"code": "type-source-missing", "path": source_name})
        if source.suffix.lower() != ".md" or target.suffix.lower() != ".md":
            issues.append({"code": "type-plan-not-markdown", "path": source_name})
        if source.parent != target.parent:
            issues.append(
                {"code": "type-plan-cross-directory", "path": source_name, "detail": target_name}
            )
        if doc_type not in config["types"]:
            issues.append(
                {"code": "type-plan-type-invalid", "path": source_name, "detail": str(doc_type)}
            )
        elif target.name != prefixed_name(source.name, doc_type, config):
            issues.append(
                {"code": "type-plan-target-invalid", "path": source_name, "detail": target.name}
            )
        if target in seen_targets:
            issues.append({"code": "type-plan-target-duplicate", "path": target_name})
        seen_targets.add(target)
        if target.exists() and target != source:
            issues.append({"code": "type-target-exists", "path": target_name})
        operations.append({"source": source, "target": target, "type": doc_type})
    return operations, issues


def rewrite_wikilinks(text: str, old_stem: str, new_stem: str) -> str:
    def replace(match: re.Match[str]) -> str:
        target = match.group(2)
        normalized = target.replace("\\", "/")
        if "/" in normalized:
            parts = normalized.split("/")
            if parts[-1] == old_stem:
                parts[-1] = new_stem
                target = "/".join(parts)
        elif normalized == old_stem:
            target = new_stem
        return match.group(1) + target + match.group(3)

    return WIKILINK_RE.sub(replace, text)


def rewrite_markdown_links(text: str, reference: Path, source: Path, target: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        destination = match.group(2)
        base, separator, fragment = destination.partition("#")
        if not base or base.startswith("/") or re.match(r"^[a-z][a-z0-9+.-]*:", base, re.I):
            return match.group(0)
        decoded = unquote(base)
        if (reference.parent / decoded).resolve() != source.resolve():
            return match.group(0)
        relative = os.path.relpath(target, reference.parent).replace(os.sep, "/")
        if base.startswith("./") and not relative.startswith("."):
            relative = f"./{relative}"
        rewritten_base = quote(relative) if unquote(base) != base else relative
        rewritten = rewritten_base + (separator + fragment if separator else "")
        return match.group(1) + rewritten + match.group(3)

    return MARKDOWN_LINK_RE.sub(replace, text)


def rebase_markdown_links(text: str, source: Path, target: Path) -> str:
    """Keep relative outbound Markdown links stable when their document moves."""

    def replace(match: re.Match[str]) -> str:
        destination = match.group(2)
        base, separator, fragment = destination.partition("#")
        if not base or base.startswith("/") or re.match(r"^[a-z][a-z0-9+.-]*:", base, re.I):
            return match.group(0)
        decoded = unquote(base)
        resolved = (source.parent / decoded).resolve()
        relative = os.path.relpath(resolved, target.parent).replace(os.sep, "/")
        if base.startswith("./") and not relative.startswith("."):
            relative = f"./{relative}"
        rewritten_base = quote(relative) if unquote(base) != base else relative
        rewritten = rewritten_base + (separator + fragment if separator else "")
        return match.group(1) + rewritten + match.group(3)

    return MARKDOWN_LINK_RE.sub(replace, text)


def reference_files(root: Path) -> list[Path]:
    ignored = {".git"}
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".md", ".canvas"}
        and not any(part in ignored for part in path.relative_to(root).parts)
    )


def apply_plan(root: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    root = root.resolve()
    original_stem_counts: dict[str, int] = {}
    for path in root.rglob("*.md"):
        if ".git" not in path.relative_to(root).parts:
            original_stem_counts[path.stem] = original_stem_counts.get(path.stem, 0) + 1

    prepared: list[dict[str, Any]] = []
    for operation in operations:
        source: Path = operation["source"]
        updated = set_frontmatter_scalar(
            source.read_text(encoding="utf-8"), "type", operation["type"]
        )
        prepared.append({**operation, "content": updated})

    changed_references: set[str] = set()
    for operation in prepared:
        source: Path = operation["source"]
        target: Path = operation["target"]
        target.write_text(operation["content"], encoding="utf-8")
        if target != source:
            source.unlink()

    for path in reference_files(root):
        text = path.read_text(encoding="utf-8")
        updated = text
        for operation in prepared:
            source: Path = operation["source"]
            target: Path = operation["target"]
            if source == target:
                continue
            if original_stem_counts.get(source.stem) == 1:
                updated = rewrite_wikilinks(updated, source.stem, target.stem)
            if path.suffix.lower() == ".md":
                updated = rewrite_markdown_links(updated, path, source, target)
            source_rel = str(source.relative_to(root)).replace("\\", "/")
            target_rel = str(target.relative_to(root)).replace("\\", "/")
            updated = updated.replace(source_rel, target_rel).replace(
                quote(source_rel), quote(target_rel)
            )
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed_references.add(str(path.relative_to(root)))
    return {
        "applied_count": len(prepared),
        "renamed_count": sum(item["source"] != item["target"] for item in prepared),
        "reference_file_count": len(changed_references),
        "changed_reference_files": sorted(changed_references),
    }
