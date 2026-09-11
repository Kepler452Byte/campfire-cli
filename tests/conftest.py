from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    campfire_home = tmp_path / "_campfire"
    monkeypatch.setenv("CAMPFIRE_HOME", str(campfire_home))
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(tmp_path / "_global_skills"))
    config = campfire_home / "workspaces" / "test" / "config"
    config.mkdir(parents=True)
    (tmp_path / "mynote").mkdir()
    (tmp_path / "mywork").mkdir()
    (tmp_path / "_收件箱").mkdir()
    (campfire_home / "registry.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "default_workspace": "test",
                "workspaces": {"test": {"path": str(tmp_path)}},
            }
        ),
        encoding="utf-8",
    )
    (config / "governance.json").write_text(
        json.dumps(
            {
                "managed_roots": [],
                "inbox": "_收件箱",
                "domain_marker": "_领域.md",
                "ignored_directories": ["assets", "archive", "generated"],
            }
        ),
        encoding="utf-8",
    )
    (config / "document-types.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scope_roots": ["mynote", "mywork"],
                "ignored_directories": ["assets", "generated"],
                "exempt_basenames": ["_领域.md"],
                "profiles": {"project-docs": ["tech-spec"]},
                "types": {
                    "knowledge": {"prefix": "知识-", "label": "知识"},
                    "tech-spec": {"prefix": "技术-", "label": "技术"},
                },
            }
        ),
        encoding="utf-8",
    )
    (config / "frontmatter-schema.json").write_text(
        json.dumps(
            {
                "version": 1,
                "field_order": [
                    "name",
                    "description",
                    "type",
                    "status",
                    "created",
                    "updated",
                    "tags",
                ],
                "base": {
                    "required": [
                        "name",
                        "description",
                        "type",
                        "status",
                        "created",
                        "updated",
                        "tags",
                    ],
                    "enums": {"status": ["draft", "current", "archived"]},
                    "lists": ["tags"],
                    "dates": ["created", "updated"],
                },
                "profiles": {},
            }
        ),
        encoding="utf-8",
    )
    (config / "skills.json").write_text(
        json.dumps(
            {
                "version": 1,
                "targets": [str(tmp_path / "_global_skills")],
                "managed_skills": [
                    "campfire-workspace-governance",
                    "campfire-conversation-intake",
                    "campfire-inbox-triage",
                    "mynote-knowledge-governance",
                    "mywork-project-docs-governance",
                    "mywork-task-governance",
                ],
                "unknown_skill_policy": "ignore",
                "orphaned_skill_policy": "report",
            }
        ),
        encoding="utf-8",
    )
    (config / "bases.json").write_text(
        json.dumps(
            {
                "version": 1,
                "target": "治理视图",
                "managed_bases": [
                    "Vault文档治理.base",
                    "项目文档.base",
                    "待归档文档.base",
                    "收件箱治理.base",
                    "任务工作台.base",
                ],
                "unknown_base_policy": "ignore",
                "orphaned_base_policy": "report",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path
