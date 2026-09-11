"""
SPEC:
  name: frontmatter_apply
  purpose: 执行已逐字段审批的 frontmatter 治理计划
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 仅写入 approved true 且 value 非 null 的字段
    - 保留正文与未审批字段
  safety:
    - 预检存在问题时不写入
    - 不移动、改名或删除文件，不编造字段值
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from campfire_cli.common.documents.document_types import safe_path, set_frontmatter_scalar


def render(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def preflight(
    root: Path, plan: dict[str, Any], schema: dict[str, Any]
) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    allowed = set(schema.get("base", {}).get("required", []))
    for profile in schema.get("profiles", {}).values():
        allowed.update(profile.get("required", []))
        allowed.update(profile.get("optional", []))
    operations = []
    issues = []
    for item in plan.get("items", []):
        try:
            path = safe_path(root, item.get("path", ""))
        except (ValueError, TypeError):
            issues.append(
                {"code": "frontmatter-plan-path-invalid", "path": str(item.get("path", ""))}
            )
            continue
        approved = {
            k: v.get("value")
            for k, v in item.get("fields", {}).items()
            if v.get("approved") is True
        }
        if not approved:
            continue
        if not path.is_file():
            issues.append({"code": "frontmatter-source-missing", "path": item.get("path", "")})
        for field, value in approved.items():
            if field not in allowed:
                issues.append(
                    {
                        "code": "frontmatter-field-unknown",
                        "path": item.get("path", ""),
                        "detail": field,
                    }
                )
            if value is None:
                issues.append(
                    {
                        "code": "frontmatter-approved-null",
                        "path": item.get("path", ""),
                        "detail": field,
                    }
                )
        operations.append((path, approved))
    return operations, issues


def apply(operations: list[tuple[Path, dict[str, Any]]]) -> int:
    changed = 0
    for path, fields in operations:
        original = path.read_text(encoding="utf-8")
        updated = original
        for field, value in fields.items():
            updated = set_frontmatter_scalar(updated, field, render(value))
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed
