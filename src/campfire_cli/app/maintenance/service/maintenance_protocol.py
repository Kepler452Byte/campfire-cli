from __future__ import annotations

from typing import Protocol

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    DomainState,
    Issue,
    MaintenancePlan,
    MaintenanceRunRecord,
    SpaceState,
)


class MaintenanceRepositoryProtocol(Protocol):
    def replace_current_state(
        self,
        documents: list[DocumentState],
        issues: list[Issue],
        spaces: list[SpaceState],
        domains: list[DomainState],
    ) -> None: ...
    def save_run(self, run: MaintenanceRunRecord) -> None: ...
    def save_plan(self, plan: MaintenancePlan) -> None: ...
    def load_plan(self, plan_id: str) -> MaintenancePlan: ...
