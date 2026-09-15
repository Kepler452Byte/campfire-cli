from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel


class CommandFollowUp(BaseModel):
    """Describe one deterministic governance command that a caller should run next."""

    command: Literal["maintenance sync"]
    workspace: str
    scope: str


def maintenance_sync_follow_up(workspace: str, scopes: Iterable[str]) -> list[CommandFollowUp]:
    """Build one sync follow-up at the smallest scope containing all changes."""

    paths = [PurePosixPath(scope.strip("/")) for scope in dict.fromkeys(scopes) if scope]
    if not paths:
        return []
    common = list(paths[0].parts)
    for path in paths[1:]:
        shared: list[str] = []
        for left, right in zip(common, path.parts, strict=False):
            if left != right:
                break
            shared.append(left)
        common = shared
        if not common:
            break
    scope = PurePosixPath(*common).as_posix() if common else "."
    return [CommandFollowUp(command="maintenance sync", workspace=workspace, scope=scope)]
