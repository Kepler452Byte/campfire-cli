from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field

from campfire_cli.common.exceptions import GovernanceBlockedError


class SkillInfo(BaseModel):
    name: str
    description: str = ""
    path: str
    status: str = "unknown"


class SkillResult(BaseModel):
    status: str
    skills: list[SkillInfo] = Field(default_factory=list)
    operations: list[dict[str, str]] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)
    content: str | None = None
    adopted: list[dict[str, str]] = Field(default_factory=list)
    completed_operations: list[dict[str, str]] = Field(default_factory=list)
    preserved_files: list[str] = Field(default_factory=list)


def resource_digest(content: bytes | None) -> str:
    return sha256(content).hexdigest() if content is not None else "missing"


@dataclass(frozen=True)
class OwnedFile:
    path: str
    kind: str


@dataclass
class Registry:
    distribution: str
    skills: list[str]
    hints: list[str]
    files: list[OwnedFile]

    @classmethod
    def load(cls, raw: bytes, distribution: str) -> Registry:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("distribution") != distribution:
                raise ValueError("identity")
            skills, hints, files = data["skills"], data["hints"], data["files"]
            if not all(isinstance(items, list) for items in (skills, hints, files)):
                raise ValueError("lists")
            if not all(isinstance(item, str) for item in [*skills, *hints]):
                raise ValueError("paths")
            if not all(Path(item).is_absolute() for item in [*skills, *hints]):
                raise ValueError("absolute paths")
            owned: list[OwnedFile] = []
            for item in files:
                if not isinstance(item, dict) or not all(
                    isinstance(item.get(key), str) for key in ("path", "kind")
                ):
                    raise ValueError("files")
                if item["kind"] not in {"skill", "hint"}:
                    raise ValueError("kind")
                owned.append(OwnedFile(item["path"], item["kind"]))
            if len({item.path for item in owned}) != len(owned):
                raise ValueError("duplicate paths")
            return cls(distribution, skills, hints, owned)
        except (ValueError, KeyError, TypeError) as exc:
            raise GovernanceBlockedError(
                "Resource registry is invalid; preserve it and repair explicitly",
                code="invalid-registry",
            ) from exc

    def encode(self) -> bytes:
        return (
            json.dumps(asdict(self), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        ).encode()


@dataclass(frozen=True)
class Change:
    path: Path
    before: str
    content: bytes | None
    action: str

    def describe(self) -> dict[str, str]:
        return {
            "path": str(self.path),
            "action": self.action,
            "expected_hash": self.before,
            "new_hash": resource_digest(self.content),
        }
