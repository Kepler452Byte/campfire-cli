from pathlib import Path

import pytest

from campfire_cli.config.defaults import effective_config


def test_user_config_deep_merges_mappings_and_replaces_lists(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        "version: 1\n"
        "governance:\n  inbox: inbox\n"
        "skills:\n  targets: [/tmp/skills]\n",
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
