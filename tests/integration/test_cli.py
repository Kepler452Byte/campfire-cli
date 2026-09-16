from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from campfire_cli.main import app

runner = CliRunner()


def test_public_tree_exposes_only_current_document_workflow() -> None:
    result = runner.invoke(app, ["tree"])
    assert result.exit_code == 0, result.output
    assert "document" in result.output
    assert "maintenance" in result.output
    assert "archive" not in result.output
    assert "decision" not in result.output


def test_document_apply_requires_path_option() -> None:
    result = runner.invoke(app, ["document", "apply", "--type", "task"])
    assert result.exit_code != 0
    assert "--path" in result.output


def test_removed_lifecycle_filter_is_not_public() -> None:
    result = runner.invoke(app, ["document", "list", "--lifecycle", "proposed"])
    assert result.exit_code != 0


def test_document_type_list_is_structured(workspace: Path) -> None:
    result = runner.invoke(app, ["--workspace", "test", "document", "type", "list"])
    assert result.exit_code == 0, result.output
    names = {item["name"] for item in json.loads(result.output)["types"]}
    assert {"prd", "trd", "human-request", "task"} <= names
    assert not {"issue", "product-spec", "tech-spec", "requirement-doc"} & names
