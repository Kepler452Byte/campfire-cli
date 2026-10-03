from pathlib import Path

from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.config.defaults import config_section


def test_scanner_only_skips_prefixed_directories_inside_a_scope(workspace: Path) -> None:
    domain = workspace / "mywork/Example"
    domain.mkdir()
    ordinary = [domain / name / f"记录-{name}.md" for name in ("assets", "archive", "generated")]
    for path in ordinary:
        path.parent.mkdir()
        path.write_text("普通内容。\n", encoding="utf-8")
    system_note = domain / "_generated/相关文档-Example.md"
    system_note.parent.mkdir()
    system_note.write_text("派生内容。\n", encoding="utf-8")

    scanned = iter_documents(workspace, config_section("document_types"), roots=[domain])

    assert set(scanned) == set(ordinary)


def test_scanner_allows_an_explicit_underscored_scope_root(workspace: Path) -> None:
    request = workspace / "_待用户确认/请求-确认.md"
    request.write_text("待确认。\n", encoding="utf-8")

    scanned = iter_documents(
        workspace,
        config_section("document_types"),
        roots=[workspace / "_待用户确认"],
    )

    assert scanned == [request]
