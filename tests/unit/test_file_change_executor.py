from pathlib import Path

import pytest

from campfire_cli.common.filesystem import FileChangeExecutor, FileChangeSet, FileWrite
from campfire_cli.common.filesystem.atomic import atomic_write as real_atomic_write


def test_change_set_restores_all_files_when_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    first = vault / "first.md"
    second = vault / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    calls = 0

    def fail_second_write(path: Path, content: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected commit failure")
        real_atomic_write(path, content)

    monkeypatch.setattr("campfire_cli.common.filesystem.change_set.atomic_write", fail_second_write)

    with pytest.raises(OSError, match="injected commit failure"):
        FileChangeExecutor(vault, state).execute(
            FileChangeSet(
                writes=(
                    FileWrite(first, "first-after\n"),
                    FileWrite(second, "second-after\n"),
                )
            )
        )

    assert first.read_text(encoding="utf-8") == "first-before\n"
    assert second.read_text(encoding="utf-8") == "second-before\n"
