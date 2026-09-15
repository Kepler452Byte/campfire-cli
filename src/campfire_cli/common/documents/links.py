"""Extract and resolve explicit document references without business orchestration."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

WIKILINK_RE = re.compile(r"(!?)\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(([^)]+)\)")
FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class LinkReference:
    raw_target: str
    relation_type: str
    syntax: str
    line: int


@dataclass(frozen=True)
class LinkResolution:
    matches: tuple[Path, ...]
    external: bool = False

    @property
    def status(self) -> str:
        if len(self.matches) == 1:
            return "resolved"
        return "ambiguous" if self.matches else "missing"


def without_code(text: str) -> str:
    """Remove code contents while preserving line numbers for link evidence."""

    def preserve_lines(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return INLINE_CODE_RE.sub("", FENCED_CODE_RE.sub(preserve_lines, text))


def extract_link_references(text: str) -> list[LinkReference]:
    cleaned = without_code(text)
    references: list[tuple[int, LinkReference]] = []
    for match in WIKILINK_RE.finditer(cleaned):
        relation_type = "embed" if match.group(1) else "wikilink"
        references.append(
            (
                match.start(),
                LinkReference(
                    raw_target=match.group(2).strip(),
                    relation_type=relation_type,
                    syntax="wiki",
                    line=cleaned.count("\n", 0, match.start()) + 1,
                ),
            )
        )
    for match in MARKDOWN_LINK_RE.finditer(cleaned):
        relation_type = "embed" if match.group(1) else "markdown-link"
        references.append(
            (
                match.start(),
                LinkReference(
                    raw_target=match.group(2).strip(),
                    relation_type=relation_type,
                    syntax="markdown",
                    line=cleaned.count("\n", 0, match.start()) + 1,
                ),
            )
        )
    return [reference for _offset, reference in sorted(references, key=lambda item: item[0])]


def stem_index(paths: set[Path]) -> dict[str, tuple[Path, ...]]:
    values: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(paths, key=lambda item: item.as_posix().casefold()):
        values[path.stem].append(path)
    return {stem: tuple(items) for stem, items in values.items()}


def resolve_link_reference(
    vault_root: Path,
    source: Path,
    reference: LinkReference,
    candidates: set[Path],
    by_stem: dict[str, tuple[Path, ...]],
) -> LinkResolution:
    raw = unquote(reference.raw_target.strip().strip("<>")).replace("\\", "/")
    target = raw.split("#", 1)[0]
    if not target:
        return LinkResolution((), external=True)
    if reference.relation_type in {"markdown-link", "embed"} and EXTERNAL_SCHEME_RE.match(target):
        return LinkResolution((), external=True)

    if reference.syntax == "wiki":
        return _resolve_wikilink(vault_root, source, target, candidates, by_stem)
    candidate = (
        vault_root / target.lstrip("/") if target.startswith("/") else source.parent / target
    ).resolve()
    matches = (candidate,) if candidate in candidates else ()
    return LinkResolution(matches)


def resolve_declared_reference(
    vault_root: Path,
    source: Path,
    raw_target: str,
    candidates: set[Path],
    by_stem: dict[str, tuple[Path, ...]],
) -> LinkResolution:
    raw = raw_target.strip()
    match = WIKILINK_RE.fullmatch(raw)
    target = match.group(2) if match else raw
    return _resolve_wikilink(vault_root, source, target, candidates, by_stem)


def _resolve_wikilink(
    vault_root: Path,
    source: Path,
    raw_target: str,
    candidates: set[Path],
    by_stem: dict[str, tuple[Path, ...]],
) -> LinkResolution:
    target = unquote(raw_target.strip()).replace("\\", "/")
    if "/" not in target:
        stem = target[:-3] if target.lower().endswith(".md") else target
        return LinkResolution(by_stem.get(stem, ()))
    options = [vault_root / target, source.parent / target]
    if not target.lower().endswith(".md"):
        options.extend([vault_root / f"{target}.md", source.parent / f"{target}.md"])
    matches = tuple(
        sorted(
            {option.resolve() for option in options if option.resolve() in candidates},
            key=lambda item: item.as_posix().casefold(),
        )
    )
    return LinkResolution(matches)
