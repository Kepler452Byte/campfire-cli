from campfire_cli.common.documents.markdown import parse_document


def test_malformed_yaml_is_recovered_without_aborting() -> None:
    document = parse_document("---\nname: | invalid\ntype: knowledge\n---\n# title\n")
    assert document.has_frontmatter
    assert document.frontmatter["type"] == "knowledge"
