from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from campfire_cli import __version__
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
from campfire_cli.common.package_version import (
    default_align_command,
    detect_install_method,
    fetch_latest_version,
    is_newer_version,
    spawn_detached_updater,
)
from campfire_cli.config.defaults import effective_config
from campfire_cli.config.settings import WorkspaceSettings, campfire_home

PACKAGE_NAME = "campfire-cli"


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
    def setup_global_resources(cls) -> dict:
        """无 Workspace 时的降级 setup：同步不依赖 Manifest 的全局资源，跳过其余步骤。"""
        return {
            "status": "needs-input",
            "message": (
                "未指定 Workspace：已同步全局治理资源；接入 Workspace 后可执行完整 setup。"
                "按场景选择以下入口之一"
            ),
            "paths": [
                {
                    "scenario": "接入已有 Vault（目录已存在，含或不含 .campfire.yaml）",
                    "command": "campfire setup --workspace <vault路径> --default",
                },
                {
                    "scenario": "从零创建新 Workspace（初始化目录结构并注册）",
                    "command": "campfire workspace create --id <id> --path <路径> --default",
                },
                {
                    "scenario": "已注册 Workspace 的本机资源全量对齐",
                    "command": "campfire upgrade",
                },
            ],
            "resources": {
                "skills": cls.build_skill().sync(dry_run=False).model_dump(mode="json"),
                "agent_hints": cls._inject_hints(),
            },
            "skipped": [
                "workspace-registration",
                "manifest",
                "config-check",
                "bases",
                "document-index",
                "health-check",
            ],
        }

    @classmethod
    def upgrade(cls, skip_package: bool = False) -> dict:
        """一条幂等命令完成 campfire 升级：更新 Python 包本身，再对齐治理资源。

        包更新通过检测到的安装方式（uv tool / pipx）在独立进程中执行，
        完成后由新版 CLI 自动执行资源对齐；离线、已是最新、editable 或
        无法识别安装方式时跳过包更新，仅对齐本机资源。
        """
        home = campfire_home()
        upgrade_database(home / "campfire.db")
        package = cls._plan_package_update(skip_package)
        if package["action"] == "updater-spawned":
            return {
                "status": "ok",
                "database": {"status": "up-to-date"},
                "package": package,
                "resources": "deferred",
                "note": (
                    "更新器已启动：等待本进程退出后更新 Python 包，"
                    "并自动执行 campfire upgrade --skip-package 对齐治理资源"
                ),
            }
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
            "package": package,
            "skills": cls.build_skill().sync(dry_run=False).model_dump(mode="json"),
            "agent_hints": cls._inject_hints(),
            "workspaces": workspaces,
        }

    @staticmethod
    def _plan_package_update(skip_package: bool) -> dict[str, object]:
        installed = __version__
        latest = fetch_latest_version(PACKAGE_NAME)
        package: dict[str, object] = {
            "installed": installed,
            "latest": latest,
            "update_available": latest is not None and is_newer_version(latest, installed),
        }
        if skip_package:
            package["action"] = "skipped-by-flag"
        elif latest is None:
            package["action"] = "skipped-offline"
        elif not package["update_available"]:
            package["action"] = "up-to-date"
        else:
            install = detect_install_method(PACKAGE_NAME)
            align = default_align_command()
            if install.update_command is not None and align is not None:
                spawn_detached_updater(install.update_command, align)
                package["action"] = "updater-spawned"
                package["update_command"] = install.update_command
            else:
                package["action"] = f"skipped-{install.manager}"
                if install.hint:
                    package["hint"] = install.hint
        return package

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
