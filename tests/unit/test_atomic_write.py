from __future__ import annotations

from pathlib import Path

from campfire_cli.common.filesystem.atomic import atomic_write


def test_atomic_write_produces_lf_only_bytes(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "生成文档.md"
    atomic_write(target, "# 标题\n\n内容\n")
    assert b"\r" not in target.read_bytes()
