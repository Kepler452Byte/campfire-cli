from __future__ import annotations

from pathlib import Path

import pytest

from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceEntry, WorkspaceRegistry


@pytest.fixture(autouse=True)
def _isolate_agent_hints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """所有测试的全局资源写入一律落在临时目录。"""
    monkeypatch.setenv("CAMPFIRE_AGENT_HINT_PATH", str(tmp_path / "agent-hints"))
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(tmp_path / "agent-skills"))


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
    (tmp_path / ".campfire.yaml").write_text(
        "schema_version: 1\nworkspace:\n  id: test\n  name: Test\n"
        "  governance_version: 1\nprojects: []\n",
        encoding="utf-8",
    )
    SqliteWorkspaceRepository(campfire_home).save_registry(
        WorkspaceRegistry(
            default_workspace="test",
            workspaces={"test": WorkspaceEntry(path=str(tmp_path))},
        )
    )
    return tmp_path
