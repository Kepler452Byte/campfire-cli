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
from campfire_cli.app.workspace.repository.adoption_repository import SqliteAdoptionRepository
from campfire_cli.app.workspace.repository.restructure_repository import (
    SqliteRestructureRepository,
)
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.adoption_service import AdoptionService
from campfire_cli.app.workspace.service.config_service import WorkspaceConfigService
from campfire_cli.app.workspace.service.domain_restructure_service import (
    DomainRestructureService,
)
from campfire_cli.app.workspace.service.restructure_service import RestructureService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.agent_hints import default_hint_paths, inject_agent_hint
from campfire_cli.common.database import create_sqlite_engine, open_session, upgrade_database
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.config.defaults import effective_config
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


@dataclass
class AppContainer:
    settings: WorkspaceSettings
    maintenance: MaintenanceService
    restructure: RestructureService
    domain_restructure: DomainRestructureService
    adoption: AdoptionService
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
        return {
            **setup_result.model_dump(mode="json"),
            "resources": {
                "config": WorkspaceConfigService(settings).check().model_dump(mode="json"),
                "skills": container.skill.sync(dry_run=False).model_dump(mode="json"),
                "bases": container.base.sync(dry_run=False).model_dump(mode="json"),
                "agent_hints": cls._inject_hints(),
            },
            "health": container.maintenance.check(summary=True).model_dump(mode="json"),
        }

    @classmethod
    def upgrade(cls) -> dict:
        """对齐本机治理资源与当前包版本：Schema 迁移、Skill、Base 与提示词路标。"""
        home = campfire_home()
        upgrade_database(home / "campfire.db")
        workspaces = []
        for workspace_id in SqliteWorkspaceRepository(home).load_registry().workspaces:
            container = cls.build(workspace_id)
            workspaces.append(
                {
                    "workspace_id": workspace_id,
                    "bases": container.base.sync(dry_run=False).model_dump(mode="json"),
                }
            )
        return {
            "status": "ok",
            "database": {"status": "up-to-date"},
            "skills": cls.build_skill().sync(dry_run=False).model_dump(mode="json"),
            "agent_hints": cls._inject_hints(),
            "workspaces": workspaces,
        }

    @staticmethod
    def _inject_hints() -> list[dict[str, str]]:
        return [
            {"path": str(path), "action": inject_agent_hint(path)}
            for path in default_hint_paths()
        ]

    @classmethod
    def build_skill(cls) -> SkillService:
        """Build the global Skill service without requiring a registered Workspace."""
        home = campfire_home()
        try:
            config = effective_config(home / "config.yml")
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"无法加载 Campfire config.yml：{exc}") from exc
        settings = WorkspaceSettings(
            workspace_id="",
            vault_root=home,
            state_root=home,
            governance=config["governance"],
            document_types=config["document_types"],
            frontmatter_schema=config["frontmatter_schema"],
            skills=config["skills"],
            bases=config["bases"],
        )
        return SkillService(settings, SkillRepository())

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
        adoption = AdoptionService(
            settings,
            SqliteAdoptionRepository(session, resolution.workspace_id),
            SqliteWorkspaceRepository(governance_root),
            maintenance,
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
            adoption=adoption,
            skill=skill,
            base=base,
            decision=decision,
        )
