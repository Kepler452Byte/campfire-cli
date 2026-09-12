from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from campfire_cli.app.base.repository.base_repository import BaseRepository
from campfire_cli.app.base.service.base_service import BaseService
from campfire_cli.app.decision.repository.decision_repository import SqliteDecisionRepository
from campfire_cli.app.decision.service.decision_projection_service import (
    DecisionProjectionService,
)
from campfire_cli.app.decision.service.decision_service import DecisionService
from campfire_cli.app.maintenance.repository.maintenance_repository import (
    SqliteMaintenanceRepository,
)
from campfire_cli.app.maintenance.service.maintenance_service import MaintenanceService
from campfire_cli.app.skill.repository.skill_repository import SkillRepository
from campfire_cli.app.skill.service.skill_service import SkillService
from campfire_cli.app.workspace.repository.restructure_repository import (
    SqliteRestructureRepository,
)
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.restructure_service import RestructureService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.database import create_sqlite_engine, open_session, upgrade_database
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


@dataclass
class AppContainer:
    settings: WorkspaceSettings
    maintenance: MaintenanceService
    restructure: RestructureService
    skill: SkillService
    base: BaseService
    decision: DecisionService

    @classmethod
    def build(cls, workspace: str | Path | None) -> AppContainer:
        governance_root = campfire_home()
        resolution = WorkspaceService(
            governance_root, SqliteWorkspaceRepository(governance_root)
        ).resolve(str(workspace) if workspace is not None else None, Path.cwd())
        settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
        database_path = governance_root / "campfire.db"
        upgrade_database(database_path)
        engine = create_sqlite_engine(database_path)
        session = open_session(engine)
        maintenance_repository = SqliteMaintenanceRepository(
            session, resolution.workspace_id, settings.state_root
        )
        maintenance = MaintenanceService(settings, maintenance_repository)
        restructure_repository = SqliteRestructureRepository(
            session, settings.state_root, resolution.workspace_id
        )
        restructure = RestructureService(settings, restructure_repository)
        skill = SkillService(settings, SkillRepository())
        base = BaseService(settings, BaseRepository())
        decision = DecisionService(
            SqliteDecisionRepository(session, resolution.workspace_id),
            DecisionProjectionService(settings),
        )
        return cls(
            settings=settings,
            maintenance=maintenance,
            restructure=restructure,
            skill=skill,
            base=base,
            decision=decision,
        )
