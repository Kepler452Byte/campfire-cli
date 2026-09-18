"""Compile the declarative Frontmatter Profile contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from campfire_cli.common.exceptions import ConfigurationError


@dataclass(frozen=True)
class FieldRule:
    name: str
    kind: str
    required: bool
    default: Any = None
    values: tuple[str, ...] = ()
    values_from: str | None = None
    items: str | None = None
    required_when: tuple[dict[str, Any], ...] = ()

    def allowed_values(self, candidate_sets: dict[str, list[str]] | None = None) -> tuple[str, ...]:
        if self.values_from is None:
            return self.values
        return tuple((candidate_sets or {}).get(self.values_from, ()))


@dataclass(frozen=True)
class EffectiveProfile:
    name: str
    fields: tuple[FieldRule, ...]
    unknown_fields: str

    @property
    def field_order(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    @property
    def allowed(self) -> tuple[str, ...]:
        return self.field_order

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if field.required)

    @property
    def optional(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if not field.required)

    @property
    def enums(self) -> dict[str, tuple[str, ...]]:
        return {field.name: field.values for field in self.fields if field.kind == "enum"}

    @property
    def value_types(self) -> dict[str, str]:
        return {
            field.name: field.kind for field in self.fields if field.kind in {"string", "boolean"}
        }

    @property
    def lists(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if field.kind == "list")

    @property
    def dates(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if field.kind == "date")

    @property
    def conditional_required(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"when": when, "require": [field.name]}
            for field in self.fields
            for when in field.required_when
        )

    def field(self, name: str) -> FieldRule | None:
        return next((field for field in self.fields if field.name == name), None)

    def required_for(self, values: dict[str, Any]) -> tuple[str, ...]:
        return tuple(
            field.name
            for field in self.fields
            if field.required
            or any(
                all(values.get(key) == value for key, value in when.items())
                for when in field.required_when
            )
        )

    def model_dump(self, candidate_sets: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return {
            "name": self.name,
            "field_order": list(self.field_order),
            "required": list(self.required),
            "optional": list(self.optional),
            "allowed": list(self.allowed),
            "enums": {
                field.name: list(field.allowed_values(candidate_sets))
                for field in self.fields
                if field.kind == "enum"
            },
            "defaults": {
                field.name: field.default for field in self.fields if field.default is not None
            },
            "value_types": dict(self.value_types),
            "lists": list(self.lists),
            "dates": list(self.dates),
            "conditional_required": list(self.conditional_required),
            "unknown_fields": self.unknown_fields,
        }


class ProfileRegistry:
    """Compile one ordered `fields` declaration for every effective Profile."""

    def __init__(self, type_config: dict[str, Any], schema: dict[str, Any]) -> None:
        if schema.get("version") != 3:
            raise ConfigurationError("Frontmatter Schema 必须是 version 3")
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
        self,
        document_type: Any,
        _frontmatter: dict[str, Any],
        _path: Path | None = None,
    ) -> EffectiveProfile:
        resolver = self._schema.get("resolver", {})
        profile_name = resolver.get("profile_by_type", {}).get(
            document_type, resolver.get("fallback", "base")
        )
        return self.get(profile_name)

    def known_fields(self) -> set[str]:
        return {field for profile in self._profiles.values() for field in profile.allowed}

    def _compile(self, name: str, profiles: dict[str, dict[str, Any]]) -> EffectiveProfile:
        raw = profiles[name]
        parent_name = raw.get("extends")
        if name == "base" and parent_name:
            raise ConfigurationError("base Profile 不能继承其他 Profile")
        if parent_name and parent_name != "base":
            raise ConfigurationError(f"Profile {name} 只能继承 base")
        parent = self._compile("base", profiles) if parent_name else None
        fields = list(parent.fields) if parent else []
        raw_fields = raw.get("fields", {})
        if not isinstance(raw_fields, dict):
            raise ConfigurationError(f"Profile {name}.fields 必须是映射")
        positions = {field.name: index for index, field in enumerate(fields)}
        for field_name, declaration in raw_fields.items():
            field = self._field(name, field_name, declaration)
            if field_name in positions:
                if parent is None:
                    raise ConfigurationError(f"Profile {name} 字段声明无效：{field_name}")
                fields[positions[field_name]] = field
            else:
                positions[field_name] = len(fields)
                fields.append(field)
        unknown_fields = raw.get("unknown_fields", parent.unknown_fields if parent else "report")
        if unknown_fields not in {"preserve", "report"}:
            raise ConfigurationError(f"Profile {name} unknown_fields 必须是 preserve 或 report")
        return EffectiveProfile(name, tuple(fields), unknown_fields)

    @staticmethod
    def _field(profile: str, name: str, declaration: Any) -> FieldRule:
        if not isinstance(declaration, dict):
            raise ConfigurationError(f"Profile {profile} 字段声明无效：{name}")
        kind = declaration.get("kind", "string")
        if kind not in {"string", "boolean", "date", "list", "enum"}:
            raise ConfigurationError(f"Profile {profile}.{name} 包含未知 kind：{kind}")
        values = declaration.get("values", [])
        values_from = declaration.get("values_from")
        if kind == "enum" and bool(values) == bool(values_from):
            raise ConfigurationError(f"Profile {profile}.{name} 枚举必须声明 values 或 values_from")
        if kind != "enum" and (values or values_from):
            raise ConfigurationError(f"Profile {profile}.{name} 仅 enum 可声明候选值")
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ConfigurationError(f"Profile {profile}.{name}.values 必须是字符串列表")
        if values_from is not None and not isinstance(values_from, str):
            raise ConfigurationError(f"Profile {profile}.{name}.values_from 必须是字符串")
        required_when = declaration.get("required_when", [])
        if not isinstance(required_when, list) or any(
            not isinstance(item, dict) for item in required_when
        ):
            raise ConfigurationError(f"Profile {profile}.{name}.required_when 必须是对象列表")
        return FieldRule(
            name=name,
            kind=kind,
            required=bool(declaration.get("required", False)),
            default=declaration.get("default"),
            values=tuple(values),
            values_from=values_from,
            items=declaration.get("items"),
            required_when=tuple(required_when),
        )

    def _validate_resolver(self) -> None:
        resolver = self._schema.get("resolver", {})
        names = {resolver.get("fallback", "base")}
        names.update(resolver.get("profile_by_type", {}).values())
        unknown = sorted(names - self._profiles.keys())
        if unknown:
            raise ConfigurationError(f"Resolver 引用了未知 Profile：{unknown}")
