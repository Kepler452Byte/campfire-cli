from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel


class CommandFollowUp(BaseModel):
    """Describe one deterministic governance command that a caller should run next."""

    command: Literal["maintenance sync", "maintenance check"]
    workspace: str
    scope: str


def maintenance_follow_up(workspace: str, scopes: Iterable[str]) -> list[CommandFollowUp]:
    """Build the ordered, deduplicated follow-up for derived workspace maintenance."""

    unique_scopes = tuple(dict.fromkeys(scopes))
    return [
        CommandFollowUp(command=command, workspace=workspace, scope=scope)
        for command in ("maintenance sync", "maintenance check")
        for scope in unique_scopes
    ]
