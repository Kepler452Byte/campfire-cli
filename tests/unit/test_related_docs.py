from __future__ import annotations

import pytest

from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.documents.related_docs import related_documents, rewrite_related_docs


@pytest.mark.parametrize(
    "value",
    [
        "[[a.md]]",
        ["a.md"],
        ["[[a]]"],
        ["[[/a.md]]"],
        ["[[../a.md]]"],
        ["[[a//b.md]]"],
        ["[[a.md|alias]]"],
        ["[[a.md#heading]]"],
        ["[[C:\\a.md]]"],
        [None],
    ],
)
def test_invalid_relationship_syntax(value) -> None:
    assert related_documents(value, "source.md")[0].resolution == "invalid"


def test_relationship_identity_and_resolution() -> None:
    edges = related_documents(
        ["[[目录/a.md]]", "[[目录/a.md]]", "[[source.md]]", "[[missing.md]]"],
        "source.md",
        {"目录/a.md", "source.md"},
    )
    assert [edge.resolution for edge in edges] == ["resolved", "duplicate", "self", "missing"]
    assert edges[-1].target == "missing.md"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_rewrite_is_frontmatter_only_and_keeps_surrounding_fields(newline) -> None:
    header = newline.join(
        [
            "---",
            "name: 保留",
            "related_docs:",
            '  - "[[目录/a.md]]"',
            "description: |",
            "  [[目录/a.md]]",
            "tags: []",
            "---",
            "",
        ]
    )
    body = newline + "  [[目录/a.md]]" + newline + "[正文](目录/a.md)" + newline
    original = header + body
    rewritten = rewrite_related_docs(original, {"目录/a.md": "目录/b.md"})
    parsed = parse_document(rewritten)
    assert parsed.frontmatter["related_docs"] == ["[[目录/b.md]]"]
    assert parsed.frontmatter["description"] == "[[目录/a.md]]\n"
    assert parsed.frontmatter["tags"] == []
    assert parsed.body == body
    assert rewrite_related_docs(rewritten, {"目录/a.md": "目录/b.md"}) == rewritten
