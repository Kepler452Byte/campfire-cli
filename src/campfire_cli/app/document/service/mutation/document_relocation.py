from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from campfire_cli.app.document.service.mutation.type_apply import (
    rebase_markdown_links,
    rewrite_markdown_links,
    rewrite_wikilinks,
)
from campfire_cli.common.filesystem import FileWrite
from campfire_cli.common.hashing import file_sha256


def prepare_document_relocation(
    vault_root: Path,
    source: Path,
    target: Path,
    moved_text: str,
) -> tuple[list[FileWrite], list[str], dict[Path, str | None]]:
    """Prepare one document relocation and every deterministic reference rewrite."""

    references = _reference_files(vault_root)
    unique_stem = sum(path.stem == source.stem for path in references if path.suffix == ".md") == 1
    source_relative = source.relative_to(vault_root).as_posix()
    target_relative = target.relative_to(vault_root).as_posix()
    writes: dict[Path, str] = {}
    changed: list[str] = []
    expected = {path: file_sha256(path) for path in references}
    for reference in references:
        text = moved_text if reference == source else reference.read_text(encoding="utf-8")
        updated = text.replace(source_relative, target_relative).replace(
            quote(source_relative), quote(target_relative)
        )
        if unique_stem and source.stem != target.stem:
            updated = rewrite_wikilinks(updated, source.stem, target.stem)
        if reference.suffix.lower() == ".md":
            updated = rewrite_markdown_links(updated, reference, source, target)
            if reference == source and source.parent != target.parent:
                updated = rebase_markdown_links(updated, source, target)
        output = target if reference == source else reference
        if reference == source or updated != text:
            writes[output] = updated
        if reference != source and updated != text:
            changed.append(reference.relative_to(vault_root).as_posix())
    return [FileWrite(path, text) for path, text in writes.items()], changed, expected


def _reference_files(vault_root: Path) -> list[Path]:
    ignored = {".git", ".campfire"}
    return sorted(
        path
        for path in vault_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".md", ".canvas"}
        and not any(part in ignored for part in path.relative_to(vault_root).parts)
    )
