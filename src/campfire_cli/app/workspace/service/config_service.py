from __future__ import annotations

from typing import Any

from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceConfigCheckResult
from campfire_cli.config.defaults import config_section
from campfire_cli.config.settings import WorkspaceSettings


class WorkspaceConfigService:
    """Validate packaged product defaults and one Workspace's effective contracts."""

    def __init__(self, settings: WorkspaceSettings) -> None:
        self.settings = settings

    def check(self) -> WorkspaceConfigCheckResult:
        issues: list[dict[str, Any]] = []
        checked = ["config.yml"]
        self._check_workspace_template(issues)
        self._check_policy_lists(issues)
        self._check_document_types(issues)
        self._check_profiles(issues)
        self._check_named_list("skills", self.settings.skills, "managed_skills", issues)
        self._check_named_list("bases", self.settings.bases, "managed_bases", issues)
        for field in (
            "inbox",
            "space_marker",
            "domain_marker",
            "related_limit",
            "related_min_score",
            "cross_domain_related_limit",
            "cross_domain_min_score",
        ):
            if not self.settings.governance.get(field):
                self._issue(issues, "governance", field, "required-value-missing")
        return WorkspaceConfigCheckResult(
            status="ok" if not issues else "issues-found", checked=checked, issues=issues
        )

    def _check_workspace_template(self, issues: list[dict[str, Any]]) -> None:
        config = config_section("workspace")
        directories = config.get("system_directories", [])
        spaces = config.get("spaces", [])
        self._unique("workspace", "system_directories", directories, issues)
        ids = [item.get("id") for item in spaces if isinstance(item, dict)]
        paths = [item.get("path") for item in spaces if isinstance(item, dict)]
        self._unique("workspace", "spaces.id", ids, issues)
        self._unique("workspace", "spaces.path", paths, issues)
        system_roots = {str(item).split("/", 1)[0] for item in directories}
        for index, item in enumerate(spaces):
            if not isinstance(item, dict):
                self._issue(issues, "workspace", f"spaces.{index}", "object-required")
                continue
            for field in ("id", "name", "path", "type"):
                if not item.get(field):
                    self._issue(
                        issues,
                        "workspace",
                        f"spaces.{index}.{field}",
                        "required-value-missing",
                    )
            if item.get("path") in system_roots:
                self._issue(
                    issues,
                    "workspace",
                    f"spaces.{index}.path",
                    "system-space-path-conflict",
                )

    def _check_policy_lists(self, issues: list[dict[str, Any]]) -> None:
        for name, fields in (
            ("project", ("statuses",)),
            ("archive", ("reasons", "reasons_requiring_successor")),
            ("issues", ("warning_codes",)),
        ):
            config = config_section(name)
            for field in fields:
                self._unique(name, field, config.get(field), issues)
        archive = config_section("archive")
        unknown = set(archive.get("reasons_requiring_successor", [])) - set(
            archive.get("reasons", [])
        )
        for value in sorted(unknown):
            self._issue(
                issues,
                "archive",
                "reasons_requiring_successor",
                "unknown-reference",
                value,
            )

    def _check_document_types(self, issues: list[dict[str, Any]]) -> None:
        config = self.settings.document_types
        types = config.get("types")
        if not isinstance(types, dict) or not types:
            self._issue(issues, "document_types", "types", "mapping-required")
            return
        prefixes = [item.get("prefix") for item in types.values() if isinstance(item, dict)]
        self._unique("document_types", "types.prefix", prefixes, issues)
        for name, item in types.items():
            if not isinstance(item, dict) or not item.get("prefix") or not item.get("label"):
                self._issue(issues, "document_types", f"types.{name}", "invalid-type")
        for profile, names in config.get("profiles", {}).items():
            for name in names:
                if name not in types:
                    self._issue(
                        issues,
                        "document_types",
                        f"profiles.{profile}",
                        "unknown-reference",
                        name,
                    )

    def _check_profiles(self, issues: list[dict[str, Any]]) -> None:
        config = self.settings.frontmatter_schema
        profiles = config.get("profiles")
        if not isinstance(profiles, dict) or "base" not in profiles:
            self._issue(issues, "frontmatter_schema", "profiles.base", "mapping-required")
            return
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                self._issue(
                    issues, "frontmatter_schema", f"profiles.{name}", "invalid-profile"
                )
                continue
            parent = profile.get("extends")
            if parent and (parent != "base" or name == "base"):
                self._issue(
                    issues,
                    "frontmatter_schema",
                    f"profiles.{name}.extends",
                    "invalid-profile-inheritance",
                    parent,
                )
            self._unique(
                "frontmatter_schema",
                f"profiles.{name}.field_order",
                profile.get("field_order", []),
                issues,
            )
            value_types = profile.get("value_types", {})
            if not isinstance(value_types, dict) or any(
                not isinstance(field, str) or expected not in {"string", "boolean"}
                for field, expected in value_types.items()
            ):
                self._issue(
                    issues,
                    "frontmatter_schema",
                    f"profiles.{name}.value_types",
                    "invalid-value-types",
                )
        resolver = config.get("resolver", {})
        referenced = [resolver.get("fallback")]
        referenced.extend(resolver.get("profile_by_type", {}).values())
        referenced.extend(resolver.get("profile_by_governance", {}).values())
        for name in referenced:
            if name not in profiles:
                self._issue(
                    issues,
                    "frontmatter_schema",
                    "resolver",
                    "unknown-reference",
                    name,
                )

    def _check_named_list(
        self,
        filename: str,
        config: dict[str, Any],
        field: str,
        issues: list[dict[str, Any]],
    ) -> None:
        self._unique(filename, field, config.get(field), issues)

    @classmethod
    def _unique(
        cls,
        filename: str,
        field: str,
        values: Any,
        issues: list[dict[str, Any]],
    ) -> None:
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item for item in values
        ):
            cls._issue(issues, filename, field, "non-empty-string-list-required")
            return
        duplicates = sorted({item for item in values if values.count(item) > 1})
        for value in duplicates:
            cls._issue(issues, filename, field, "duplicate-value", value)

    @staticmethod
    def _issue(
        issues: list[dict[str, Any]],
        path: str,
        field: str,
        code: str,
        actual: Any = None,
    ) -> None:
        issues.append({"code": code, "path": path, "field": field, "actual": actual})
