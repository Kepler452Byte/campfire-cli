from __future__ import annotations

from typing import Protocol

from campfire_cli.app.document.schema import DocumentIndexResult
from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DomainState,
    Issue,
    MaintenanceRunRecord,
    SpaceState,
)


class DocumentIndexMaintainerProtocol(Protocol):
    """Expose only the index maintenance operations needed by Maintenance."""

    def rebuild(self) -> DocumentIndexResult: ...

    def reconcile(self) -> DocumentIndexResult: ...


class MaintenanceRepositoryProtocol(Protocol):
    def replace_current_state(
        self,
        issues: list[Issue],
        spaces: list[SpaceState],
        domains: list[DomainState],
    ) -> None: ...
    def save_run(self, run: MaintenanceRunRecord) -> None: ...
    def replace_scope_index(
        self,
        scope: str,
        domains: list[DomainState],
    ) -> None: ...
