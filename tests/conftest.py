from __future__ import annotations

from pathlib import Path

import pytest

from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceEntry, WorkspaceRegistry


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    campfire_home = tmp_path / "_campfire"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(tmp_path / "_global_skills"))
    (tmp_path / "mynote").mkdir()
    (tmp_path / "mywork").mkdir()
    (tmp_path / "mynote/_空间.md").write_text(
        "---\nname: 知识\nspace_id: knowledge\nspace_type: knowledge\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "mywork/_空间.md").write_text(
        "---\nname: 工作\nspace_id: work\nspace_type: work\nstatus: active\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "_收件箱").mkdir()
    SqliteWorkspaceRepository(campfire_home).save_registry(
        WorkspaceRegistry(
            default_workspace="test",
            workspaces={"test": WorkspaceEntry(path=str(tmp_path))},
        )
    )
    return tmp_path
