"""Compile declarative document Profile contracts into effective rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from campfire_cli.common.documents.frontmatter_schema import is_project_context
from campfire_cli.common.exceptions import ConfigurationError


def ordered_union(*values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in values for item in group))


@dataclass(frozen=True)
class EffectiveProfile:
    name: str
    field_order: tuple[str, ...]
    required: tuple[str, ...]
    optional: tuple[str, ...]
    enums: dict[str, tuple[str, ...]]
    value_types: dict[str, str]
    lists: tuple[str, ...]
    dates: tuple[str, ...]
    conditional_required: tuple[dict[str, Any], ...]
    unknown_fields: str

    @property
    def allowed(self) -> tuple[str, ...]:
        return ordered_union(self.required, self.optional)

    def conditional_fields(self, values: dict[str, Any]) -> tuple[str, ...]:
        return ordered_union(
            *[
                condition["require"]
                for condition in self.conditional_required
                if all(values.get(key) == value for key, value in condition["when"].items())
            ]
        )

    def required_for(self, values: dict[str, Any]) -> tuple[str, ...]:
        return ordered_union(self.required, self.conditional_fields(values))

    def model_dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "field_order": list(self.field_order),
            "required": list(self.required),
            "optional": list(self.optional),
            "allowed": list(self.allowed),
            "enums": {key: list(value) for key, value in self.enums.items()},
            "value_types": dict(self.value_types),
            "lists": list(self.lists),
            "dates": list(self.dates),
            "conditional_required": list(self.conditional_required),
            "unknown_fields": self.unknown_fields,
        }


class ProfileRegistry:
    """Compile declarative profile inheritance into immutable effective profiles."""

    def __init__(self, type_config: dict[str, Any], schema: dict[str, Any]) -> None:
        if schema.get("version") != 2:
            raise ConfigurationError("Frontmatter Schema 必须是 version 2")
        self._type_config = type_config
        self._schema = schema
        raw_profiles = schema.get("profiles", {})
        if "base" not in raw_profiles:
            raise ConfigurationError("Frontmatter Schema 缺少 base Profile")
        self._profiles = {name: self._compile(name, raw_profiles) for name in raw_profiles}
        self._validate_resolver()

    def list(self) -> list[EffectiveProfile]:
        return list(self._profiles.values())

    def get(self, name: str) -> EffectiveProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise ConfigurationError(f"未知 Frontmatter Profile：{name}") from exc

    def resolve(
        self, document_type: Any, frontmatter: dict[str, Any], path: Path | None = None
    ) -> EffectiveProfile:
        resolver = self._schema.get("resolver", {})
        direct = (
            resolver.get("profile_by_type", {}).get(document_type)
            if isinstance(document_type, str)
            else None
        )
        if direct:
            return self.get(direct)
        governance_types = set(
            resolver.get("governance_types", {}).get("project-docs", [])
        )
        if (
            isinstance(document_type, str)
            and document_type in governance_types
            and is_project_context(path)
        ):
            profile = resolver.get("profile_by_governance", {}).get("project-docs")
            if profile:
                return self.get(profile)
        return self.get(resolver.get("fallback", "base"))

    def known_fields(self) -> set[str]:
        return {field for profile in self._profiles.values() for field in profile.allowed}

    def _compile(self, name: str, raw_profiles: dict[str, dict[str, Any]]) -> EffectiveProfile:
        raw = raw_profiles[name]
        parent_name = raw.get("extends")
        if name == "base" and parent_name:
            raise ConfigurationError("base Profile 不能继承其他 Profile")
        if parent_name and parent_name != "base":
            raise ConfigurationError(f"Profile {name} 只能继承 base")
        parent = self._compile("base", raw_profiles) if parent_name else None
        required = ordered_union(parent.required if parent else (), raw.get("required", []))
        optional = ordered_union(parent.optional if parent else (), raw.get("optional", []))
        enums = dict(parent.enums) if parent else {}
        enums.update({key: tuple(value) for key, value in raw.get("enums", {}).items()})
        value_types = dict(parent.value_types) if parent else {}
        value_types.update(raw.get("value_types", {}))
        lists = ordered_union(parent.lists if parent else (), raw.get("lists", []))
        dates = ordered_union(parent.dates if parent else (), raw.get("dates", []))
        conditions = tuple(
            [*(parent.conditional_required if parent else ()), *raw.get("conditional_required", [])]
        )
        order = tuple(raw.get("field_order", parent.field_order if parent else []))
        unknown_fields = raw.get("unknown_fields", parent.unknown_fields if parent else "preserve")
        if unknown_fields not in {"preserve", "report"}:
            raise ConfigurationError(f"Profile {name} unknown_fields 必须是 preserve 或 report")
        allowed = set(required) | set(optional)
        constrained = set(enums) | set(value_types) | set(lists) | set(dates)
        condition_fields = {
            field
            for condition in conditions
            for field in [*condition.get("when", {}), *condition.get("require", [])]
        }
        invalid_constraints = sorted((constrained | condition_fields) - allowed)
        if invalid_constraints:
            raise ConfigurationError(f"Profile {name} 约束了未允许字段：{invalid_constraints}")
        invalid_types = sorted(
            {value for value in value_types.values() if value not in {"string", "boolean"}}
        )
        if invalid_types:
            raise ConfigurationError(f"Profile {name} 包含未知 value_types：{invalid_types}")
        if set(order) != allowed:
            missing = sorted(allowed - set(order))
            extra = sorted(set(order) - allowed)
            raise ConfigurationError(
                f"Profile {name} field_order 与允许字段不一致；missing={missing}, extra={extra}"
            )
        return EffectiveProfile(
            name=name,
            field_order=order,
            required=required,
            optional=optional,
            enums=enums,
            value_types=value_types,
            lists=lists,
            dates=dates,
            conditional_required=conditions,
            unknown_fields=unknown_fields,
        )

    def _validate_resolver(self) -> None:
        resolver = self._schema.get("resolver", {})
        names = {
            resolver.get("fallback", "base"),
            *resolver.get("profile_by_type", {}).values(),
            *resolver.get("profile_by_governance", {}).values(),
        }
        unknown = sorted(names - self._profiles.keys())
        if unknown:
            raise ConfigurationError(f"Resolver 引用了未知 Profile：{unknown}")
