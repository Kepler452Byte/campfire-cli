from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from campfire_cli.common.documents.frontmatter_schema import merged_rules, resolve_profile
from campfire_cli.common.documents.markdown import parse_document

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class GovernanceRuleEngine:
    """Single entry point for document and template contract validation."""

    def __init__(self, type_config: dict[str, Any], schema: dict[str, Any]) -> None:
        self._type_config = type_config
        self._schema = schema

    def check_document(self, root: Path, path: Path) -> list[dict[str, Any]]:
        relative = path.relative_to(root).as_posix()
        parsed = parse_document(path.read_text(encoding="utf-8"))
        if not parsed.has_frontmatter:
            return [{"code": "frontmatter-missing", "path": relative}]
        frontmatter = parsed.frontmatter
        issues: list[dict[str, Any]] = []
        document_type = frontmatter.get("type")
        types = self._type_config.get("types", {})
        if not isinstance(document_type, str) or not document_type:
            issues.append({"code": "document-type-missing", "path": relative})
        elif document_type not in types:
            issues.append(
                {"code": "document-type-invalid", "path": relative, "detail": str(document_type)}
            )
        elif not path.name.startswith(types[document_type]["prefix"]):
            issues.append(
                {
                    "code": "document-prefix-mismatch",
                    "path": relative,
                    "detail": types[document_type]["prefix"],
                }
            )
        rules = self._rules(document_type, path, frontmatter)
        for field in rules["required"]:
            value = frontmatter.get(field)
            if field not in frontmatter or value is None or value == "":
                issues.append(
                    {"code": "frontmatter-field-missing", "path": relative, "detail": field}
                )
        for field in rules["lists"]:
            if field in frontmatter and not isinstance(frontmatter[field], list):
                issues.append(
                    {"code": "frontmatter-list-invalid", "path": relative, "detail": field}
                )
        for field in rules["dates"]:
            value = frontmatter.get(field)
            if value is not None and not DATE_RE.fullmatch(str(value)):
                issues.append(
                    {"code": "frontmatter-date-invalid", "path": relative, "detail": field}
                )
        for field, allowed in rules["enums"].items():
            value = frontmatter.get(field)
            if value is not None and value not in allowed:
                issues.append(
                    {
                        "code": "frontmatter-enum-invalid",
                        "path": relative,
                        "detail": f"{field}={value}",
                        "field": field,
                        "actual": value,
                        "allowed": allowed,
                    }
                )
        issues.extend(self._state_invariants(relative, path, document_type, frontmatter))
        return issues

    def check_templates(self, root: Path, skills_root: Path) -> list[dict[str, Any]]:
        if not skills_root.is_dir():
            return []
        issues: list[dict[str, Any]] = []
        for path in sorted(skills_root.rglob("*.md")):
            parsed = parse_document(path.read_text(encoding="utf-8"))
            document_type = parsed.frontmatter.get("type")
            if not parsed.has_frontmatter or document_type not in self._type_config.get(
                "types", {}
            ):
                continue
            rules = self._rules(document_type, path, parsed.frontmatter)
            for field, allowed in rules["enums"].items():
                value = parsed.frontmatter.get(field)
                if value is not None and value not in allowed:
                    issues.append(
                        {
                            "code": "template-enum-invalid",
                            "path": path.relative_to(root).as_posix(),
                            "detail": f"{field}={value}",
                            "field": field,
                            "actual": value,
                            "allowed": allowed,
                        }
                    )
        return issues

    def known_fields(self) -> set[str]:
        fields = set(self._schema.get("field_order", []))
        for rules in [self._schema.get("base", {}), *self._schema.get("profiles", {}).values()]:
            for key in ("required", "optional", "lists", "dates"):
                fields.update(rules.get(key, []))
            fields.update(rules.get("enums", {}))
        return fields

    def validate_patch(
        self,
        root: Path,
        path: Path,
        current: dict[str, Any],
        patch: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Validate values a migration would write, without requiring unrelated fields."""
        merged = {**current, **patch}
        rules = self._rules(merged.get("type"), path, merged)
        relative = path.relative_to(root).as_posix()
        issues: list[dict[str, Any]] = []
        for field in rules["lists"]:
            if field in patch and not isinstance(patch[field], list):
                issues.append(
                    {"code": "frontmatter-list-invalid", "path": relative, "detail": field}
                )
        for field in rules["dates"]:
            value = patch.get(field)
            if value is not None and not DATE_RE.fullmatch(str(value)):
                issues.append(
                    {"code": "frontmatter-date-invalid", "path": relative, "detail": field}
                )
        for field, allowed in rules["enums"].items():
            value = patch.get(field)
            if value is not None and value not in allowed:
                issues.append(
                    {
                        "code": "frontmatter-enum-invalid",
                        "path": relative,
                        "detail": f"{field}={value}",
                        "field": field,
                        "actual": value,
                        "allowed": allowed,
                    }
                )
        return issues

    def _rules(self, document_type: Any, path: Path, frontmatter: dict[str, Any]) -> dict[str, Any]:
        profile = resolve_profile(document_type, frontmatter, self._schema, path)
        return merged_rules(profile, self._schema)

    @staticmethod
    def _state_invariants(
        relative: str,
        path: Path,
        document_type: Any,
        frontmatter: dict[str, Any],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        status = frontmatter.get("status")
        lifecycle = frontmatter.get("lifecycle")
        in_archive = "archive" in path.parts
        if in_archive != (status == "archived" and lifecycle == "archived") and (
            in_archive or status == "archived" or lifecycle == "archived"
        ):
            issues.append({"code": "document-archive-state-mismatch", "path": relative})
        if document_type != "task":
            return issues
        if status == "draft":
            issues.append({"code": "task-status-draft-invalid", "path": relative})
        if frontmatter.get("task_source") == "assigned" and not frontmatter.get("requested_by"):
            issues.append(
                {"code": "task-requested-by-missing", "path": relative, "detail": "assigned"}
            )
        if lifecycle == "blocked" and not frontmatter.get("blocked_reason"):
            issues.append({"code": "task-blocked-reason-missing", "path": relative})
        if lifecycle == "completed":
            for field in ("completed", "result_summary", "verification"):
                if not frontmatter.get(field):
                    issues.append(
                        {
                            "code": "task-completion-evidence-missing",
                            "path": relative,
                            "detail": field,
                        }
                    )
        elif lifecycle != "archived" and frontmatter.get("completed"):
            issues.append(
                {
                    "code": "task-completed-date-premature",
                    "path": relative,
                    "detail": str(lifecycle),
                }
            )
        return issues
