from __future__ import annotations

import pytest

from campfire_cli.app.maintenance.service.moc_service import (
    direct_templates,
    generate_project_domain_content,
    replace_generated_region,
)
from campfire_cli.app.workspace.schema.workspace_schema import Domain


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
        ("<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->"),
    ],
)
def test_generated_region_rejects_ambiguous_boundaries(text: str) -> None:
    with pytest.raises(ValueError):
        replace_generated_region(text, "新内容")


def test_domain_moc_lists_only_templates_owned_by_that_domain(tmp_path) -> None:
    template_dir = tmp_path / "_模板"
    template_dir.mkdir()
    template = template_dir / "模板-版本发布清单.md"
    template.write_text("# 模板\n", encoding="utf-8")
    (template_dir / "草稿.md").write_text("# 非模板\n", encoding="utf-8")
    domain = Domain(
        id="project-example",
        name="Example",
        path=tmp_path,
        space_id="work",
        type="project-domain",
        governance="project-docs",
        moc="MOC-Example",
    )

    templates = direct_templates(domain)
    generated = generate_project_domain_content(
        domain,
        [domain],
        [],
        templates,
        "_领域.md",
        {},
    )

    assert templates == [template]
    assert "## 文档模板" in generated
    assert "[[_模板/模板-版本发布清单|模板-版本发布清单]]" in generated
    assert "草稿" not in generated


def test_domain_moc_omits_template_section_without_direct_templates(tmp_path) -> None:
    domain = Domain(
        id="project-example",
        name="Example",
        path=tmp_path,
        space_id="work",
        type="project-domain",
        governance="project-docs",
        moc="MOC-Example",
    )

    generated = generate_project_domain_content(
        domain,
        [domain],
        [],
        [],
        "_领域.md",
        {},
    )

    assert "## 文档模板" not in generated
