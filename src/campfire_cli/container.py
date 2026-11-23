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
from campfire_cli.app.workspace.repository.manifest_repository import WorkspaceManifestRepository
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
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.common.package_updater import PackageUpdater
from campfire_cli.config.settings import AgentResourceSettings, WorkspaceSettings, campfire_home


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
    def build_upgrade(cls):
        from campfire_cli.app.system.service.upgrade_service import UpgradeService

        return UpgradeService(
            cls.build_system(),
            cls._package_updater(campfire_home()),
            cls.build_job(),
        )

    @staticmethod
    def _package_updater(home: Path) -> PackageUpdater:
        return PackageUpdater("campfire-cli", "campfire", home)

    @staticmethod
    def build_workspace():
        home = campfire_home()
        return WorkspaceService(home, FilesystemWorkspaceRepository(home))

    @staticmethod
    def build_script():
        from campfire_cli.app.script.service.script_service import ScriptService
        from campfire_cli.config.defaults import config_section

        return ScriptService(campfire_home(), config_section("scripts"))

    @classmethod
    def build_job(cls):
        import sys

        from campfire_cli.app.job.adapter.launchd_scheduler import LaunchdScheduler
        from campfire_cli.app.job.adapter.systemd_scheduler import SystemdScheduler
        from campfire_cli.app.job.adapter.windows_scheduler import WindowsScheduler
        from campfire_cli.app.job.repository.database import JobDatabase
        from campfire_cli.app.job.repository.job_repository import JobRepository
        from campfire_cli.app.job.repository.run_repository import RunRepository
        from campfire_cli.app.job.schema.retention_schema import RetentionPolicy
        from campfire_cli.app.job.service.job_service import JobService
        from campfire_cli.config.defaults import config_section

        home = campfire_home()
        config = config_section("jobs")
        scheduler = {
            "linux": SystemdScheduler,
            "darwin": LaunchdScheduler,
            "win32": WindowsScheduler,
        }[sys.platform](home)
        registry = FilesystemWorkspaceRepository(home)

        def resolve(identity: str) -> Path:
            resolution = WorkspaceService(home, registry).resolve(identity, safe_cwd())
            return Path(resolution.workspace)

        database = JobDatabase(home / "jobs/jobs.db")
        return JobService(
            home,
            scheduler,
            JobRepository(home, database),
            RunRepository(database),
            RetentionPolicy(**config["retention"]),
            resolve,
            config,
            cls.build_script(),
            cls._package_updater(home).active_status,
        )

    @classmethod
    def build_skill(cls) -> AgentResourceService:
        """Build the global Skill service without requiring a registered Workspace."""
        settings = AgentResourceSettings.load()
        return AgentResourceService(settings, AgentResourceRepository(settings.state_root))

    @classmethod
    def workspace_skill_roots(
        cls, workspace: str | None
    ) -> tuple[tuple[Path, ...], list[dict[str, str]]]:
        resolution = cls.build_workspace().resolve(workspace, safe_cwd())
        return WorkspaceManifestRepository().skill_roots(Path(resolution.workspace))

    @classmethod
    def build(cls, workspace: str | Path | None) -> AppContainer:
        governance_root = campfire_home()
        workspace_repository = FilesystemWorkspaceRepository(governance_root)
        resolution = WorkspaceService(governance_root, workspace_repository).resolve(
            str(workspace) if workspace is not None else None, safe_cwd()
        )
        workspace_root = Path(resolution.workspace)
        skill_roots, _ = WorkspaceManifestRepository().skill_roots(workspace_root)
        settings = WorkspaceSettings.load(
            resolution.workspace_id, workspace_root, skill_roots=skill_roots
        )
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
        skill = cls.build_skill()
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
