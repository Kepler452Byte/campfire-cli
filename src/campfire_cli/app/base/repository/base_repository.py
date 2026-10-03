from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from campfire_cli.common.filesystem import atomic_write


class BaseRepository:
    def source_root(self) -> Path:
        return Path(str(files("campfire_cli.resources") / "bases"))

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write(self, path: Path, content: str) -> None:
        atomic_write(path, content)
