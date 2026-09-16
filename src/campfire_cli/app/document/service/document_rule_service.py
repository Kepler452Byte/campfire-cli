from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.profile_registry import EffectiveProfile, ProfileRegistry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.frontmatter_format import ordered_keys
from campfire_cli.common.documents.markdown import parse_document

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class DocumentRuleService:
    """Single entry point for document and template contract validation."""

    def __init__(self, type_config: dict[str, Any], schema: dict[str, Any]) -> None:
        self._type_config = type_config
        self._schema = schema
        self._profiles = ProfileRegistry(type_config, schema)

    def check_document(self, root: Path, path: Path) -> list[dict[str, Any]]:
        return self.check_content(root, path, path.read_text(encoding="utf-8"))

    def check_content(
        self,
        root: Path,
        path: Path,
        text: str,
        profile: EffectiveProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Validate proposed Markdown without requiring it to exist on disk."""
        relative = path.relative_to(root).as_posix()
        parsed = parse_document(text)
        if not parsed.has_frontmatter:
            return [{"code": "frontmatter-missing", "path": relative}]
        frontmatter = parsed.frontmatter
        issues: list[dict[str, Any]] = []
        document_type = frontmatter.get("type")
        types = self._type_config.get("types", {})
        if isinstance(document_type, list):
            issues.append(
                {
                    "code": "document-type-multiple",
                    "path": relative,
                    "field": "type",
                    "actual": document_type,
                    "allowed": sorted(types),
                }
            )
        elif not isinstance(document_type, str) or not document_type:
            issues.append({"code": "document-type-missing", "path": relative, "field": "type"})
        elif document_type not in types:
            issues.append(
                {
                    "code": "document-type-invalid",
                    "path": relative,
                    "detail": str(document_type),
                    "field": "type",
                    "actual": document_type,
                    "allowed": sorted(types),
                }
            )
        elif not path.name.startswith(types[document_type]["prefix"]):
            issues.append(
                {
                    "code": "document-prefix-mismatch",
                    "path": relative,
                    "detail": types[document_type]["prefix"],
                    "field": "filename",
                    "actual": path.name,
                    "allowed": [types[document_type]["prefix"]],
                }
            )
        elif prefixed_name(path.name, document_type, self._type_config) != path.name:
            issues.append(
                {
                    "code": "document-name-bracket-category",
                    "path": relative,
                    "field": "filename",
                    "actual": path.name,
                    "allowed": [prefixed_name(path.name, document_type, self._type_config)],
                }
            )
        rules = (profile or self._profiles.resolve(document_type, frontmatter, path)).model_dump()
        actual_order = list(frontmatter)
        expected_order = ordered_keys(
            [(key, []) for key in actual_order], list(rules["field_order"])
        )
        if actual_order != expected_order:
            issues.append(
                {
                    "code": "frontmatter-field-order-invalid",
                    "path": relative,
                    "field": "frontmatter",
                    "actual": actual_order,
                    "allowed": expected_order,
                }
            )
        conditional = {
            field
            for condition in rules["conditional_required"]
            if all(frontmatter.get(key) == value for key, value in condition["when"].items())
            for field in condition["require"]
        }
        for field in dict.fromkeys([*rules["required"], *conditional]):
            if field not in frontmatter:
                issues.append(
                    {
                        "code": "frontmatter-field-missing",
                        "path": relative,
                        "detail": field,
                        "field": field,
                    }
                )
                continue
            value = frontmatter[field]
            if value is None or value == "" or field in conditional and not value:
                issues.append(
                    {
                        "code": "frontmatter-field-empty",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": value,
                    }
                )
        for field in frontmatter:
            if rules["unknown_fields"] == "report" and field not in rules["allowed"]:
                issues.append(
                    {
                        "code": "frontmatter-field-not-allowed",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": frontmatter[field],
                        "allowed": rules["allowed"],
                    }
                )
        for field in rules["lists"]:
            if field in frontmatter and not isinstance(frontmatter[field], list):
                issues.append(
                    {
                        "code": "frontmatter-list-invalid",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": frontmatter[field],
                        "allowed": ["list"],
                    }
                )
        for field in rules["dates"]:
            value = frontmatter.get(field)
            if value is not None and not DATE_RE.fullmatch(str(value)):
                issues.append(
                    {
                        "code": "frontmatter-date-invalid",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": value,
                        "allowed": ["YYYY-MM-DD"],
                    }
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
        for field, expected in rules["value_types"].items():
            value = frontmatter.get(field)
            if value is not None and not self._matches_value_type(value, expected):
                issues.append(
                    {
                        "code": "frontmatter-type-invalid",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": type(value).__name__,
                        "allowed": [expected],
                    }
                )
        issues.extend(self._state_invariants(relative, path, document_type, frontmatter))
        return issues

    def check_collection(self, root: Path, paths: list[Path]) -> list[dict[str, Any]]:
        """Validate invariants that require seeing more than one document."""
        current_documents: dict[tuple[str, str, str, str], list[str]] = {}
        for path in paths:
            frontmatter = parse_document(path.read_text(encoding="utf-8")).frontmatter
            document_type = frontmatter.get("type")
            if document_type not in {"moc", "product-spec"}:
                continue
            if frontmatter.get("status") != "current":
                continue
            project = frontmatter.get("project")
            domain = frontmatter.get("domain")
            if not project or not domain:
                continue
            physical_domain = path.parent.relative_to(root).as_posix()
            key = (physical_domain, str(project), str(domain), str(document_type))
            current_documents.setdefault(key, []).append(path.relative_to(root).as_posix())
        issues: list[dict[str, Any]] = []
        for (_physical, project, domain, document_type), matches in sorted(
            current_documents.items()
        ):
            if len(matches) < 2:
                continue
            issues.append(
                {
                    "code": "project-doc-current-conflict",
                    "path": matches[0],
                    "detail": f"{project}/{domain}/{document_type}",
                    "actual": sorted(matches),
                    "allowed": ["one-current-document"],
                }
            )
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
        return self._profiles.known_fields()

    def field_order_for(self, frontmatter: dict[str, Any], path: Path | None = None) -> list[str]:
        """返回文档在当前治理契约下的有效 Profile 字段序。

        写入口修改 frontmatter 后必须按此序插入新增字段，否则文档立即产生
        frontmatter-field-order-invalid。
        """
        profile = self._profiles.resolve(frontmatter.get("type"), frontmatter, path)
        return list(profile.field_order)

    def validate_patch(
        self,
        root: Path,
        path: Path,
        current: dict[str, Any],
        patch: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Validate values a restructure would write, without requiring unrelated fields."""
        merged = {**current, **patch}
        rules = self._rules(merged.get("type"), path, merged)
        relative = path.relative_to(root).as_posix()
        issues: list[dict[str, Any]] = []
        for field in patch:
            if rules["unknown_fields"] == "report" and field not in rules["allowed"]:
                issues.append(
                    {
                        "code": "frontmatter-field-not-allowed",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": patch[field],
                        "allowed": rules["allowed"],
                    }
                )
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
        for field, expected in rules["value_types"].items():
            value = patch.get(field)
            if (
                field in patch
                and value is not None
                and not self._matches_value_type(value, expected)
            ):
                issues.append(
                    {
                        "code": "frontmatter-type-invalid",
                        "path": relative,
                        "detail": field,
                        "field": field,
                        "actual": type(value).__name__,
                        "allowed": [expected],
                    }
                )
        return issues

    @staticmethod
    def _matches_value_type(value: Any, expected: str) -> bool:
        return isinstance(value, str) if expected == "string" else isinstance(value, bool)

    def _rules(self, document_type: Any, path: Path, frontmatter: dict[str, Any]) -> dict[str, Any]:
        return self._profiles.resolve(document_type, frontmatter, path).model_dump()

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
        in_template_directory = "_模板" in path.parts
        if document_type == "template" and path.parent.name != "_模板":
            issues.append({"code": "template-directory-required", "path": relative})
        elif in_template_directory and document_type != "template":
            issues.append({"code": "template-directory-type-mismatch", "path": relative})
        in_archive = "archive" in path.parts
        if in_archive != (status == "archived" and lifecycle == "archived") and (
            in_archive or status == "archived" or lifecycle == "archived"
        ):
            issues.append({"code": "document-archive-state-mismatch", "path": relative})
        if document_type != "task":
            return issues
        if status == "draft":
            issues.append({"code": "task-status-draft-invalid", "path": relative})
        if lifecycle not in {"completed", "archived"} and frontmatter.get("completed"):
            issues.append(
                {
                    "code": "task-completed-date-premature",
                    "path": relative,
                    "detail": str(lifecycle),
                }
            )
        return issues
