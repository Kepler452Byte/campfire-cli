from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from campfire_cli.config.settings import campfire_home
from campfire_cli.main import app

runner = CliRunner()


def cli(*arguments: str) -> dict:
    result = runner.invoke(app, list(arguments))
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def document(workspace: Path) -> Path:
    cli(
        "workspace",
        "project",
        "create",
        "--id",
        "product",
        "--name",
        "Product",
        "--path",
        "mywork/product",
        "--confirm",
    )
    args = [
        "document",
        "apply",
        "--path",
        "mywork/product/Example",
        "--type",
        "knowledge",
        "--set",
        "description=Example",
        "--set",
        "document_status=current",
    ]
    preview = cli(*args)
    created = cli(*args, "--expected-hash", preview["expected_hash"], "--confirm")
    return workspace / created["target"]


def test_rebuild_and_no_change_sync_report_current_index_separately(workspace: Path) -> None:
    document(workspace)
    first = cli("workspace", "rebuild", "--confirm")
    total = cli("document", "list")["total"]
    assert first["indexed_document_count"] >= total > 0
    assert first["index_available"] is True
    assert first["index_full_rebuild"] is True
    assert first["write_performed"] is False
    assert first["write_performed_scope"] == "markdown-files"
    again = cli("workspace", "rebuild", "--confirm")
    assert again["indexed_document_count"] == first["indexed_document_count"]
    assert again["index_content_changed_document_count"] == 0
    assert again["index_processed_document_count"] > 0
    assert again["index_generation"] > first["index_generation"]
    cli("maintenance", "sync", "--scope", "mywork/product")
    cli("document", "list")
    quiet = cli("maintenance", "sync", "--scope", "mywork/product")
    assert quiet["index_available"] is True
    assert quiet["index_processed_document_count"] == 0
    assert quiet["indexed_document_count"] > 0
    assert quiet["write_performed"] is False


def test_known_errors_have_details_in_setup_rebuild_and_reports(workspace: Path) -> None:
    path = document(workspace)
    text = path.read_text().replace(
        "tags: []", 'tags: []\nrelated_docs:\n- "[[mywork/product/知识-Missing.md]]"'
    )
    path.write_text(text)
    (workspace / "_待用户确认").rmdir()
    setup = cli("setup", "--path", str(workspace), "--default")
    assert setup["status"] == "needs-review"
    issues = {item["code"]: item for item in setup["health"]["issues"]}
    for code in ("related-docs-missing", "human-request-root-missing"):
        assert issues[code]["message"]
        assert issues[code]["suggestion"]
        assert issues[code]["detail"]
        assert issues[code]["actual"]
    assert issues["related-docs-missing"]["field"] == "related_docs"
    assert issues["human-request-root-missing"]["field"] == "governance.human_request_root"
    rebuilt = cli("workspace", "rebuild", "--confirm")
    assert rebuilt["status"] == "needs-review"
    assert rebuilt["index_available"] is True
    assert rebuilt["indexed_document_count"] > 0
    report_root = campfire_home() / "workspaces/test/reports"
    report = json.loads((report_root / "current.json").read_text())
    assert report["issues"] == rebuilt["issues"]
    assert "mywork/product/知识-Missing.md" in (report_root / "current.md").read_text()
    assert "_待用户确认" in (report_root / "current.md").read_text()


def test_setup_summary_verbose_and_body_link_boundary(workspace: Path) -> None:
    path = document(workspace)
    path.write_text(path.read_text() + "\n[[mywork/product/知识-Missing.md]]\n")
    compact = cli("setup", "--path", str(workspace), "--default")
    assert compact["status"] == "ok"
    assert compact["health"]["body_links_checked"] is False
    assert compact["health"]["checked_relations"] == "related_docs"
    assert compact["health"]["issue_count"] == 0
    assert "operations" not in compact["resources"]["skills"]
    assert "operation_count" in compact["resources"]["skills"]
    detailed = cli("setup", "--path", str(workspace), "--default", "--verbose")
    assert "operations" in detailed["resources"]["skills"]
    assert (
        detailed["health"]["indexed_document_count"] == compact["health"]["indexed_document_count"]
    )


def test_type_discovery_to_profile_and_apply_in_isolated_workspace(workspace: Path) -> None:
    document(workspace)
    types = cli("document", "type", "list")
    selected = next(item for item in types["types"] if item["name"] == "knowledge")
    assert selected["prefix"]
    profile = cli("document", "profile", "resolve", "--type", selected["name"])
    assert "description" in profile["profile"]["required"]
    args = [
        "document",
        "apply",
        "--path",
        "mywork/product/Discovered",
        "--type",
        selected["name"],
        "--set",
        "description=Discovered through current type contract",
    ]
    preview = cli(*args)
    assert preview["issues"] == []
    created = cli(*args, "--expected-hash", preview["expected_hash"], "--confirm")
    path = workspace / created["target"]
    assert path.name.startswith(selected["prefix"])
    assert path.is_file()
    cli("skill", "sync")
    checked = cli("skill", "check")
    assert checked["status"] == "ok"
