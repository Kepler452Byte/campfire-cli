from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from campfire_cli.app.base.repository.base_repository import BaseRepository
from campfire_cli.app.base.service.base_service import BaseService
from campfire_cli.app.maintenance.repository.maintenance_repository import (
    SqliteMaintenanceRepository,
)
from campfire_cli.app.maintenance.service.database_service import DatabaseService
from campfire_cli.app.maintenance.service.maintenance_service import MaintenanceService
from campfire_cli.app.migration.repository.migration_repository import (
    SqliteMigrationRepository,
)
from campfire_cli.app.migration.service.migration_service import MigrationService
from campfire_cli.app.skill.repository.skill_repository import SkillRepository
from campfire_cli.app.skill.service.skill_service import SkillService
from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.database import create_sqlite_engine, open_session, upgrade_database
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


@dataclass
class AppContainer:
    settings: WorkspaceSettings
    maintenance: MaintenanceService
    migration: MigrationService
    database: DatabaseService
    skill: SkillService
    base: BaseService

    @classmethod
    def build(cls, workspace: str | Path | None) -> AppContainer:
        governance_root = campfire_home()
        resolution = WorkspaceService(
            governance_root, FilesystemWorkspaceRepository(governance_root)
        ).resolve(str(workspace) if workspace is not None else None, Path.cwd())
        settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
        database_path = settings.state_root / "db" / "campfire.db"
        upgrade_database(database_path)
        engine = create_sqlite_engine(database_path)
        session = open_session(engine)
        maintenance_repository = SqliteMaintenanceRepository(session)
        maintenance = MaintenanceService(settings, maintenance_repository)
        migration_repository = SqliteMigrationRepository(session, settings.state_root)
        migration = MigrationService(settings, migration_repository)
        database = DatabaseService(settings, engine, session)
        skill = SkillService(settings, SkillRepository())
        base = BaseService(settings, BaseRepository())
        return cls(
            settings=settings,
            maintenance=maintenance,
            migration=migration,
            database=database,
            skill=skill,
            base=base,
        )
