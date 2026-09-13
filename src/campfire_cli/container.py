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
from campfire_cli.app.document.repository.document_profile_repository import (
    DocumentProfileRepository,
)
from campfire_cli.app.document.repository.document_type_repository import (
    DocumentTypeRepository,
)
from campfire_cli.app.document.service.document_profile_service import (
    DocumentProfileService,
)
from campfire_cli.app.document.service.document_type_service import DocumentTypeService
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
from campfire_cli.app.workspace.service.domain_restructure_service import (
    DomainRestructureService,
)
from campfire_cli.app.workspace.service.restructure_service import RestructureService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.database import create_sqlite_engine, open_session, upgrade_database
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


@dataclass
class AppContainer:
    settings: WorkspaceSettings
    maintenance: MaintenanceService
    restructure: RestructureService
    domain_restructure: DomainRestructureService
    skill: SkillService
    base: BaseService
    decision: DecisionService

    @classmethod
    def setup(cls, workspace: Path, make_default: bool = False) -> dict:
        """Bootstrap one device from the portable Workspace Manifest."""
        governance_root = campfire_home()
        setup_result = WorkspaceService(
            governance_root, SqliteWorkspaceRepository(governance_root)
        ).setup(workspace, make_default)
        container = cls.build(setup_result.workspace_id)
        settings = container.settings
        document_types = DocumentTypeService(
            settings.workspace_id,
            settings.state_root,
            DocumentTypeRepository(settings.state_root),
        ).sync(confirm=True)
        profiles = DocumentProfileService(
            settings.workspace_id,
            settings.vault_root,
            settings.state_root,
            settings.document_types,
            DocumentProfileRepository(settings.state_root),
        ).sync(confirm=True)
        return {
            **setup_result.model_dump(mode="json"),
            "resources": {
                "document_types": document_types,
                "document_profiles": profiles,
                "skills": container.skill.sync(dry_run=False).model_dump(mode="json"),
                "bases": container.base.sync(dry_run=False).model_dump(mode="json"),
            },
            "health": container.maintenance.check(summary=True).model_dump(mode="json"),
        }

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
        domain_restructure = DomainRestructureService(
            settings, SqliteWorkspaceRepository(governance_root), maintenance
        )
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
            domain_restructure=domain_restructure,
            skill=skill,
            base=base,
            decision=decision,
        )
