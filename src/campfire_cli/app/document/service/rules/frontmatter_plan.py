"""
SPEC:
  name: frontmatter_plan
  purpose: 生成分层 frontmatter 缺失字段的可审阅补全计划
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 从一级标题确定性建议 name
    - 对列表字段建议空列表，其余语义字段保留 null
    - 每个字段默认 approved false
  safety:
    - 不修改文档，不编造摘要、日期、状态或业务事实
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.app.document.service.rules.profile_registry import ProfileRegistry
from campfire_cli.common.documents.frontmatter_schema import parse_shape


def title(text: str) -> str | None:
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            body = text[end + 5 :]
    match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else None


def build_plan(root: Path, type_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    profiles = ProfileRegistry(type_config, schema)
    items = []
    for path in iter_documents(root, type_config):
        text = path.read_text(encoding="utf-8")
        values, kinds = parse_shape(text)
        profile = profiles.resolve(values.get("type"), values, path)
        fields = {}
        conditional = set(profile.conditional_fields(values))
        for field in profile.required_for(values):
            if field in values and (values[field] or kinds.get(field) == "list"):
                continue
            value: Any = None
            confidence = "low"
            reason = "semantic-input-required"
            if field == "name" and title(text):
                value = title(text)
                confidence = "high"
                reason = "first-heading"
            elif field in profile.lists and field not in conditional:
                value = []
                confidence = "high"
                reason = "empty-list-default"
            fields[field] = {
                "value": value,
                "confidence": confidence,
                "reason": reason,
                "approved": False,
            }
        if fields:
            items.append(
                {
                    "path": str(path.relative_to(root)),
                    "profile": profile.name,
                    "fields": fields,
                }
            )
    return {"version": 1, "schema_version": schema.get("version", 1), "items": items}
