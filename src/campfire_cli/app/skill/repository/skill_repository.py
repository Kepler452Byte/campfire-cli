from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from campfire_cli.common.filesystem import atomic_write


class SkillRepository:
    def source_root(self) -> Path:
        return Path(str(files("campfire_cli.resources") / "skills"))

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write(self, path: Path, content: str) -> None:
        atomic_write(path, content)

    def delete_files(self, root: Path, paths: list[Path]) -> None:
        root = root.resolve()
        for path in paths:
            path.resolve().relative_to(root)
            path.unlink()
        directories = sorted(
            {parent for path in paths for parent in path.parents if parent != root},
            key=lambda item: len(item.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                continue
