"""
SPEC:
  name: frontmatter_check
  purpose: 按基础字段、Profile 和类型扩展检查 Vault frontmatter
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 检查必填字段、枚举、列表和日期格式
    - 按单选 type 自动选择扩展 Profile
  safety:
    - 只读，不修改任何文档
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import (
    iter_documents,
)
from campfire_cli.common.documents.frontmatter_schema import DATE_RE, parse_shape


def check_document(
    root: Path, path: Path, type_config: dict[str, Any], schema: dict[str, Any]
) -> list[dict[str, str]]:
    rel = str(path.relative_to(root))
    values, kinds = parse_shape(path.read_text(encoding="utf-8"))
    if not values:
        return [{"code": "frontmatter-missing", "path": rel}]
    profile = ProfileRegistry(type_config, schema).resolve(values.get("type"), values, path)
    issues: list[dict[str, str]] = []
    for field in profile.required:
        if field not in values or not values[field] and kinds.get(field) != "list":
            issues.append({"code": "frontmatter-field-missing", "path": rel, "detail": field})
    for field in profile.lists:
        if field in values and kinds.get(field) != "list":
            issues.append({"code": "frontmatter-list-invalid", "path": rel, "detail": field})
    for field in profile.dates:
        if values.get(field) and not DATE_RE.fullmatch(values[field]):
            issues.append(
                {
                    "code": "frontmatter-date-invalid",
                    "path": rel,
                    "detail": f"{field}={values[field]}",
                }
            )
    for field, allowed in profile.enums.items():
        if values.get(field) and values[field] not in allowed:
            issues.append(
                {
                    "code": "frontmatter-enum-invalid",
                    "path": rel,
                    "detail": f"{field}={values[field]}",
                }
            )
    return issues


def build_result(root: Path, type_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    docs = iter_documents(root, type_config)
    issues = [
        issue
        for path in docs
        for issue in check_document(root, path, type_config, schema)
    ]
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    return {
        "status": "ok" if not issues else "issues-found",
        "document_count": len(docs),
        "issue_count": len(issues),
        "issue_counts": dict(sorted(counts.items())),
        "issues": issues,
    }
