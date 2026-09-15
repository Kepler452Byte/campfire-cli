from __future__ import annotations

import pytest

from campfire_cli.app.maintenance.service.moc_service import replace_generated_region


def test_generated_region_replaces_only_tagged_content() -> None:
    original = (
        "人工正文\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n旧内容\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n"
        "尾部正文\n"
    )

    updated = replace_generated_region(original, "新内容")

    assert updated.startswith("人工正文\n<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->")
    assert "\n新内容\n" in updated
    assert updated.endswith("<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n尾部正文\n")


@pytest.mark.parametrize(
    "text",
    [
        "没有标记",
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n只有开始",
        (
            "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n"
            "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->"
        ),
    ],
)
def test_generated_region_rejects_ambiguous_boundaries(text: str) -> None:
    with pytest.raises(ValueError):
        replace_generated_region(text, "新内容")
