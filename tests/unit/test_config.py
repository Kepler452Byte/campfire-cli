from pathlib import Path

import pytest

from campfire_cli.app.workspace.service.config_service import WorkspaceConfigService
from campfire_cli.config.defaults import effective_config
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


def test_user_config_deep_merges_mappings_and_replaces_lists(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        "version: 1\ngovernance:\n  inbox: inbox\nskills:\n  targets: [/tmp/skills]\n",
        encoding="utf-8",
    )

    config = effective_config(path)

    assert config["governance"]["inbox"] == "inbox"
    assert config["governance"]["domain_marker"] == "_领域.md"
    assert config["skills"]["targets"] == ["/tmp/skills"]


def test_user_config_rejects_unknown_top_level_sections(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("version: 1\nunknown: true\n", encoding="utf-8")

    with pytest.raises(ValueError, match="未知顶级分区"):
        effective_config(path)


def test_config_check_requires_human_request_root_to_be_indexed(
    workspace: Path,
) -> None:
    (campfire_home() / "config.yml").write_text(
        "version: 1\ndocument_types:\n  scope_roots: []\n",
        encoding="utf-8",
    )

    settings = WorkspaceSettings.load("test", workspace)
    result = WorkspaceConfigService(settings).check()

    assert result.status == "issues-found"
    assert {
        "code": "required-reference-missing",
        "path": "document_types",
        "field": "scope_roots",
        "actual": "_待用户确认",
    } in result.issues
