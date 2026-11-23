from pathlib import Path


def skill_entry(directory: Path) -> Path | None:
    """Find the exact Agent Skills entry without following a file symlink."""
    for path in directory.glob("SKILL.md", case_sensitive=True):
        if not path.is_symlink() and path.is_file():
            return path
    return None


def in_skill_package(path: Path, roots: tuple[Path, ...], *, directory: bool = False) -> bool:
    """Identify packages independently of their frontmatter."""
    folder = path if directory else path.parent
    for root in roots:
        if folder.is_relative_to(root) and any(
            skill_entry(parent) is not None
            for parent in (folder, *folder.parents)
            if parent.is_relative_to(root)
        ):
            return True
    return False
