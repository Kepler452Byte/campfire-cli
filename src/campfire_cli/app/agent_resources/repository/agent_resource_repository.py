from __future__ import annotations

from contextlib import AbstractContextManager
from importlib.resources import files
from pathlib import Path

from campfire_cli.common.filesystem.resource_files import (
    atomic_write,
    read_bytes,
    safe_path,
    write_lock,
)


class AgentResourceRepository:
    def __init__(self, state_root: Path):
        self.state_root = state_root
        self.registry_path = state_root / "agent-resources.json"

    def source_root(self) -> Path:
        return Path(str(files("campfire_cli.resources") / "skills"))

    def assets(self, names: list[str]) -> dict[str, bytes]:
        root = self.source_root()
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for name in names
            for path in sorted((root / name).rglob("*"))
            if path.is_file()
        }

    def hint(self) -> bytes:
        return (files("campfire_cli.resources") / "agent_hint.md").read_bytes().rstrip(b"\r\n")

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def read_bytes(self, path: Path) -> bytes | None:
        return read_bytes(path)

    def write(self, path: Path, content: bytes) -> None:
        atomic_write(path, content)

    def remove(self, path: Path) -> None:
        safe_path(path).unlink(missing_ok=True)

    def resolve(self, path: Path) -> Path:
        return safe_path(path)

    def lock(self, targets: list[Path]) -> AbstractContextManager[None]:
        return write_lock(self.state_root, targets)
