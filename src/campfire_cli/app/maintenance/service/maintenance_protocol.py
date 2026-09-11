from __future__ import annotations

from typing import Protocol

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    Issue,
    MaintenanceRunRecord,
)


class MaintenanceRepositoryProtocol(Protocol):
    def replace_current_state(
        self, documents: list[DocumentState], issues: list[Issue]
    ) -> None: ...
    def save_run(self, run: MaintenanceRunRecord) -> None: ...
