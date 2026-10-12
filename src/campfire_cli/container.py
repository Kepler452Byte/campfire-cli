from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from campfire_cli.app.agent_resources.repository.agent_resource_repository import (
    AgentResourceRepository,
)
from campfire_cli.app.agent_resources.service.agent_resource_service import AgentResourceService
from campfire_cli.app.base.repository.base_repository import BaseRepository
from campfire_cli.app.base.service.base_service import BaseService
from campfire_cli.app.document.repository.document_index_repository import (
    SqliteDocumentIndexRepository,
)
from campfire_cli.app.document.service.document_service import DocumentService
from campfire_cli.app.document.service.index.document_index_service import DocumentIndexService
from campfire_cli.app.maintenance.repository.maintenance_repository import (
    SqliteMaintenanceRepository,
)
from campfire_cli.app.maintenance.service.maintenance_service import MaintenanceService
from campfire_cli.app.workspace.repository.restructure_repository import (
    SqliteRestructureRepository,
)
from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.service.adoption_service import AdoptionService
from campfire_cli.app.workspace.service.domain_restructure_service import (
    DomainRestructureService,
)
from campfire_cli.app.workspace.service.restructure_service import RestructureService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.database import create_sqlite_engine, initialize_database, open_session
from campfire_cli.common.database.models import Workspace
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.defaults import effective_config
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


@dataclass
class AppContainer:
    settings: WorkspaceSettings
    document: DocumentService
    maintenance: MaintenanceService
    restructure: RestructureService
    domain_restructure: DomainRestructureService
    adoption: AdoptionService
    skill: AgentResourceService
    base: BaseService

    @staticmethod
    def build_video():
        from campfire_cli.app.video.service.video_service import VideoService
        from campfire_cli.common.media.media_backend import ProcessMediaBackend
        from campfire_cli.common.media.model_download import download_model
        from campfire_cli.common.media.video_runtime import LocalVideoRuntime
        from campfire_cli.config.defaults import config_section

        return VideoService(
            ProcessMediaBackend(),
            config_section("video"),
            campfire_home(),
            download_model,
            LocalVideoRuntime(),
        )

    def deliver_video(
        self,
        bundle: Path,
        draft: Path,
        path: str,
        *,
        confirm: bool,
        expected_plan: str | None,
    ) -> dict:
        from campfire_cli.common.exceptions import GovernanceBlockedError

        inspection = self.document.inspect(path)
        if inspection.get("issues") or not inspection.get("domain_id"):
            raise GovernanceBlockedError("目标必须是领域内通过治理检查的受管文档")
        return self.build_video().deliver(
            bundle,
            draft,
            self.settings.vault_root / inspection["path"],
            self.settings.vault_root,
            self.settings.state_root,
            confirm=confirm,
            expected_plan=expected_plan,
        )

    @classmethod
    def build_system(cls):
        from campfire_cli.app.system.service.system_service import SystemService

        return SystemService(cls.build, cls.build_skill())

    @classmethod
    def build_skill(cls) -> AgentResourceService:
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
        return AgentResourceService(settings, AgentResourceRepository())

    @classmethod
    def build(cls, workspace: str | Path | None) -> AppContainer:
        governance_root = campfire_home()
        workspace_repository = FilesystemWorkspaceRepository(governance_root)
        resolution = WorkspaceService(governance_root, workspace_repository).resolve(
            str(workspace) if workspace is not None else None, safe_cwd()
        )
        settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
        database_path = governance_root / "campfire.db"
        engine = create_sqlite_engine(database_path)
        initialize_database(engine)
        session = open_session(engine)
        with session.begin():
            session.merge(Workspace(id=resolution.workspace_id))
        project_roots = {
            project.document_domain_id: project.id
            for project in workspace_repository.list_projects(resolution.workspace_id)
        }
        document_index = DocumentIndexService(
            settings,
            SqliteDocumentIndexRepository(session, resolution.workspace_id),
            project_roots,
        )
        maintenance_repository = SqliteMaintenanceRepository(session, resolution.workspace_id)
        maintenance = MaintenanceService(settings, maintenance_repository, document_index)
        restructure_repository = SqliteRestructureRepository(
            session, settings.state_root, resolution.workspace_id
        )
        restructure = RestructureService(settings, restructure_repository)
        domain_restructure = DomainRestructureService(settings, workspace_repository)
        adoption = AdoptionService(
            settings,
            workspace_repository,
        )
        skill = AgentResourceService(settings, AgentResourceRepository())
        base = BaseService(settings, BaseRepository())
        return cls(
            settings=settings,
            document=DocumentService(settings, document_index, project_roots),
            maintenance=maintenance,
            restructure=restructure,
            domain_restructure=domain_restructure,
            adoption=adoption,
            skill=skill,
            base=base,
        )
