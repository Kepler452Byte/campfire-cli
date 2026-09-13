from __future__ import annotations

from typing import Protocol

from campfire_cli.app.workspace.schema.adoption_schema import AdoptionBatchState


class AdoptionRepositoryProtocol(Protocol):
    def save(self, state: AdoptionBatchState) -> None: ...

    def load(self, batch: str) -> AdoptionBatchState: ...
