from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from campfire_cli.config.settings import campfire_home
from campfire_cli.main import app


@pytest.mark.parametrize("document_type,profile", [("knowledge", "base"), ("task", "task")])
def test_resolve_type_without_existing_document(
    workspace: Path, document_type: str, profile: str
) -> None:
    result = CliRunner().invoke(
        app, ["--workspace", "test", "document", "profile", "resolve", "--type", document_type]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["profile"]["name"] == profile
    assert payload["type"] == document_type and payload["path"] is None


@pytest.mark.parametrize(
    "args", [[], ["--type", "knowledge", "--path", "missing.md"], ["--type", "unknown"]]
)
def test_resolve_invalid_selector(workspace: Path, args: list[str]) -> None:
    result = CliRunner().invoke(
        app, ["--workspace", "test", "document", "profile", "resolve", *args]
    )
    assert result.exit_code != 0
    assert json.loads(result.output)["code"] in {
        "profile-selector-invalid",
        "document-type-invalid",
    }


def test_show_type_returns_executable_hint(workspace: Path) -> None:
    import shlex

    runner = CliRunner()
    result = runner.invoke(app, ["--workspace", "test", "document", "profile", "show", "knowledge"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "profile-name-required"
    resolved = runner.invoke(app, shlex.split(payload["hint"])[1:])
    assert resolved.exit_code == 0, resolved.output
    assert json.loads(resolved.output)["profile"]["name"] == "base"


def test_custom_mapping_resolve_matches_apply_and_existing_path(workspace: Path) -> None:
    (campfire_home() / "config.yml").write_text(
        "version: 1\nfrontmatter_schema:\n  profiles:\n    custom:\n      extends: base\n"
        "      fields: {}\n  resolver:\n    profile_by_type:\n      knowledge: custom\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    def invoke(*args: str) -> dict:
        result = runner.invoke(app, ["--workspace", "test", *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    invoke(
        "workspace",
        "domain",
        "create",
        "--id",
        "demo",
        "--name",
        "Demo",
        "--path",
        "mynote/Demo",
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-base",
        "--confirm",
    )
    profile = invoke("document", "profile", "resolve", "--type", "knowledge")["profile"]
    created = invoke(
        "document",
        "apply",
        "--path",
        "mynote/Demo/说明",
        "--type",
        "knowledge",
        "--set",
        "description=说明",
        "--expected-hash",
        "missing",
        "--confirm",
    )
    assert created["profile"] == profile["name"] == "custom"
    existing = invoke("document", "profile", "resolve", "--path", created["target"])
    assert existing["profile"] == profile
