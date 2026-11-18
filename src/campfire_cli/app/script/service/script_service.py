"""Read local script projects without executing or modifying their files."""

import os
import stat
from pathlib import Path

from campfire_cli.app.script.schema.project_schema import validate_project_name
from campfire_cli.common.exceptions import InputError


class ScriptService:
    def __init__(self, home: Path, config: dict) -> None:
        self.root = home / config["directory"]
        self.ignored = set(config["ignored_names"])
        self.max_entries = config["max_entries"]
        self.max_file_bytes = config["max_file_bytes"]

    def projects(self) -> dict:
        if self.root.is_symlink() or self.root.is_junction():
            raise InputError("脚本预览不跟随符号链接或目录联接", code="invalid-script-path")
        if not self.root.exists():
            return {"status": "ok", "root": str(self.root), "projects": []}
        entries = self._entries(self.root, self.root)
        projects = []
        for entry in entries:
            if entry["kind"] != "directory":
                continue
            try:
                validate_project_name(entry["name"])
            except InputError:
                continue
            projects.append(entry["name"])
        return {
            "status": "ok",
            "root": str(self.root),
            "projects": projects,
        }

    def require_project(self, project: str) -> None:
        self._target(project, "")

    def directory(self, project: str, path: str = "") -> dict:
        root, target = self._target(project, path)
        if not target.is_dir():
            raise InputError("目录不存在", code="not-found")
        return {
            "status": "ok",
            "project": project,
            "path": path,
            "entries": self._entries(root, target),
        }

    def file(self, project: str, path: str) -> dict:
        _, target = self._target(project, path)
        if not target.is_file():
            raise InputError("文件不存在", code="not-found")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
        )
        try:
            with os.fdopen(os.open(target, flags), "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise InputError("仅支持预览普通文本文件", code="invalid-script-file")
                data = source.read(self.max_file_bytes + 1)
            self._target(project, path)
            if len(data) > self.max_file_bytes:
                raise InputError(
                    "文件超过预览大小上限",
                    code="invalid-script-file",
                    max_bytes=self.max_file_bytes,
                )
            if b"\0" in data:
                raise ValueError("binary")
            content = data.decode("utf-8-sig")
        except (UnicodeError, ValueError) as exc:
            raise InputError("该文件不是 UTF-8 文本，无法预览", code="invalid-script-file") from exc
        except OSError as exc:
            raise InputError("文件已变化或无法读取，请刷新", code="invalid-script-file") from exc
        return {
            "status": "ok",
            "project": project,
            "path": path,
            "content": content,
            "size": len(data),
        }

    def _target(self, project: str, path: str) -> tuple[Path, Path]:
        validate_project_name(project)
        if project in self.ignored:
            raise InputError("该目录不属于可预览的脚本项目", code="invalid-script-project")
        parts = path.split("/") if path else []
        if any(
            part in {"", ".", ".."}
            or part in self.ignored
            or "\\" in part
            or ":" in part
            or "\0" in part
            for part in parts
        ):
            raise InputError("文件路径必须位于选定脚本项目内", code="invalid-script-path")
        root = self.root / project
        target = root.joinpath(*parts)
        for entry in [
            self.root,
            root,
            *[root.joinpath(*parts[:index]) for index in range(1, len(parts) + 1)],
        ]:
            if entry.is_symlink() or entry.is_junction():
                raise InputError("脚本预览不跟随符号链接或目录联接", code="invalid-script-path")
        if not root.is_dir() or not target.exists():
            raise InputError("脚本项目或文件不存在", code="not-found")
        if not target.resolve().is_relative_to(root.resolve()):
            raise InputError("文件路径超出脚本项目", code="invalid-script-path")
        return root, target

    def _entries(self, root: Path, directory: Path) -> list[dict]:
        if directory.is_symlink() or directory.is_junction():
            raise InputError("脚本预览不跟随符号链接或目录联接", code="invalid-script-path")
        entries = []
        try:
            for index, entry in enumerate(directory.iterdir()):
                if index >= self.max_entries:
                    raise InputError(
                        "目录条目过多，无法完整预览",
                        code="invalid-script-directory",
                        max_entries=self.max_entries,
                    )
                if entry.name in self.ignored or entry.is_symlink() or entry.is_junction():
                    continue
                mode = entry.stat().st_mode
                if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
                    continue
                entries.append(
                    {
                        "name": entry.name,
                        "path": entry.relative_to(root).as_posix(),
                        "kind": "directory" if stat.S_ISDIR(mode) else "file",
                    }
                )
        except OSError as exc:
            raise InputError("无法读取脚本目录，请刷新", code="invalid-script-directory") from exc
        return sorted(
            entries,
            key=lambda entry: (
                entry["kind"] != "directory",
                entry["name"].casefold(),
                entry["name"],
            ),
        )
