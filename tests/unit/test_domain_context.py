from pathlib import Path

import pytest

from campfire_cli.common.documents.domain_context import (
    DomainContextError,
    resolve_domain_context,
)


def marker(
    path: Path,
    domain_id: str,
    *,
    parent: str | None = None,
    project: str | None = None,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"domain_id: {domain_id}"]
    if parent:
        lines.append(f"parent_domain: {parent}")
    if project:
        lines.append(f"project_id: {project}")
    lines.extend(["---", ""])
    (path / "_领域.md").write_text("\n".join(lines), encoding="utf-8")


def test_resolves_project_from_multi_level_parent_chain(tmp_path: Path) -> None:
    root = tmp_path / "project"
    child = root / "release"
    grandchild = child / "notes"
    marker(root, "project-example", project="example")
    marker(child, "project-example-release", parent="project-example")
    marker(grandchild, "project-example-release-notes", parent="project-example-release")

    context = resolve_domain_context(
        tmp_path, grandchild / "计划-Test.md", {"project-example": "example"}
    )

    assert context.root == grandchild
    assert context.domain_id == "project-example-release-notes"
    assert context.project_id == "example"


def test_resolves_unique_project_from_physical_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "project"
    child = root / "release"
    marker(root, "project-example", project="example")
    marker(child, "project-example-release")

    context = resolve_domain_context(
        tmp_path, child / "计划-Test.md", {"project-example": "example"}
    )

    assert context.project_id == "example"


def test_rejects_conflicting_projects(tmp_path: Path) -> None:
    root = tmp_path / "project"
    child = root / "release"
    marker(root, "project-example", project="example")
    marker(child, "project-example-release", parent="project-example")

    with pytest.raises(DomainContextError) as error:
        resolve_domain_context(
            tmp_path,
            child / "计划-Test.md",
            {"project-example": "example", "project-example-release": "other"},
        )

    assert error.value.code == "domain-project-conflict"


def test_rejects_missing_parent_domain(tmp_path: Path) -> None:
    child = tmp_path / "release"
    marker(child, "project-example-release", parent="project-example")

    with pytest.raises(DomainContextError) as error:
        resolve_domain_context(tmp_path, child / "计划-Test.md")

    assert error.value.code == "parent-domain-missing"


def test_rejects_parent_cycle(tmp_path: Path) -> None:
    root = tmp_path / "project"
    child = root / "release"
    marker(root, "project-example", parent="project-example-release", project="example")
    marker(child, "project-example-release", parent="project-example")

    with pytest.raises(DomainContextError) as error:
        resolve_domain_context(tmp_path, child / "计划-Test.md")

    assert error.value.code == "domain-parent-cycle"
