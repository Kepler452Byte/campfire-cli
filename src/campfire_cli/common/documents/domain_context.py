from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from campfire_cli.common.documents.markdown import parse_document


@dataclass(frozen=True)
class DomainContext:
    root: Path
    domain_id: str
    project_id: str | None


class DomainContextError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class _Marker:
    root: Path
    domain_id: str
    parent_domain: str | None
    project_id: str | None


def resolve_domain_context(
    vault_root: Path,
    path: Path,
    marker_name: str = "_领域.md",
) -> DomainContext:
    """Resolve the nearest Domain and its uniquely inherited Project."""

    root = vault_root.resolve()
    current = path.resolve().parent
    markers: list[_Marker] = []
    while current == root or root in current.parents:
        marker = current / marker_name
        if marker.is_file():
            frontmatter = parse_document(marker.read_text(encoding="utf-8")).frontmatter
            domain_id = frontmatter.get("domain_id")
            if not isinstance(domain_id, str) or not domain_id:
                raise DomainContextError("domain-id-missing", str(marker))
            parent = frontmatter.get("parent_domain")
            project = frontmatter.get("project_id") or frontmatter.get("project")
            markers.append(
                _Marker(
                    root=current,
                    domain_id=domain_id,
                    parent_domain=parent if isinstance(parent, str) and parent else None,
                    project_id=project if isinstance(project, str) and project else None,
                )
            )
        if current == root:
            break
        current = current.parent
    if not markers:
        raise DomainContextError("domain-missing", str(path))

    nearest = markers[0]
    by_id = {marker.domain_id: marker for marker in markers}
    visited: set[str] = set()
    current_marker = nearest
    while True:
        if current_marker.domain_id in visited:
            raise DomainContextError("domain-parent-cycle", current_marker.domain_id)
        visited.add(current_marker.domain_id)
        if current_marker.parent_domain is None:
            break
        parent = by_id.get(current_marker.parent_domain)
        if parent is None:
            raise DomainContextError("parent-domain-missing", current_marker.parent_domain)
        if parent.domain_id in visited:
            raise DomainContextError("domain-parent-cycle", parent.domain_id)
        if parent.root not in current_marker.root.parents:
            raise DomainContextError("domain-parent-path-mismatch", parent.domain_id)
        current_marker = parent

    projects = {marker.project_id for marker in markers if marker.project_id is not None}
    if len(projects) > 1:
        raise DomainContextError("domain-project-conflict", ",".join(sorted(projects)))
    project = next(iter(projects), None)
    return DomainContext(root=nearest.root, domain_id=nearest.domain_id, project_id=project)


def resolve_domain_by_id(
    vault_root: Path,
    domain_id: str,
    marker_name: str = "_领域.md",
) -> DomainContext:
    """Resolve exactly one declared Domain by stable id."""

    root = vault_root.resolve()
    matches: list[Path] = []
    for marker in root.rglob(marker_name):
        frontmatter = parse_document(marker.read_text(encoding="utf-8")).frontmatter
        if frontmatter.get("domain_id") == domain_id:
            matches.append(marker)
    if len(matches) != 1:
        raise DomainContextError("domain-id-not-unique", domain_id)
    return resolve_domain_context(root, matches[0].parent / "__target__.md", marker_name)
