"""
SPEC:
  name: type_plan
  purpose: 为 Vault 文档生成可审阅的 type 与文件名前缀治理计划
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 已有合法单选 type 时生成高置信度改名建议
    - 只有合法文件名前缀时生成高置信度 type 补全建议
    - 无法确定时保留待 Agent 或人类审批项
  safety:
    - 不修改任何文档
    - 所有计划项默认 approved false
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.common.documents.document_types import (
    frontmatter_value,
    prefix_type,
    prefixed_name,
)


def contextual_suggestion(path: Path) -> tuple[str | None, str]:
    value = str(path).lower()
    rules = [
        (("工作周报", "weekly"), "weekly-report"),
        (("会议记录", "会议纪要"), "meeting"),
        (("工作日志",), "work-log"),
        (("开发实验",), "experiment"),
        (("提示词", "prompt"), "prompt"),
    ]
    for needles, doc_type in rules:
        if any(needle.lower() in value for needle in needles):
            return doc_type, "path-context"
    return None, "semantic-review-required"


def plan_item(root: Path, path: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    doc_type, multiple = frontmatter_value(text, "type")
    by_prefix = prefix_type(path.name, config)
    proposed: str | None = None
    confidence = "low"
    reason = "semantic-review-required"
    if not multiple and doc_type in config["types"]:
        proposed, confidence, reason = doc_type, "high", "existing-valid-type"
    elif not multiple and not doc_type and by_prefix:
        proposed, confidence, reason = by_prefix, "high", "existing-unique-prefix"
    elif not multiple and (not doc_type or doc_type not in config["types"]):
        proposed, reason = contextual_suggestion(path)
        confidence = "medium" if proposed else "low"
    target_name = prefixed_name(path.name, proposed, config) if proposed else path.name
    if proposed is not None and proposed == doc_type and target_name == path.name and not multiple:
        return None
    rel = str(path.relative_to(root))
    target = str(path.with_name(target_name).relative_to(root))
    return {
        "source": rel,
        "target": target,
        "current_type": doc_type,
        "proposed_type": proposed,
        "confidence": confidence,
        "reason": "type-is-sequence" if multiple else reason,
        "approved": False,
    }


def build_plan(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    items = [
        item for path in iter_documents(root, config) if (item := plan_item(root, path, config))
    ]
    return {"version": 1, "contract_version": config.get("version", 1), "items": items}
