from pathlib import Path

from campfire_cli.app.base.repository.base_repository import BaseRepository
from campfire_cli.app.base.service.base_service import BaseService
from campfire_cli.config.settings import WorkspaceSettings


def test_base_semantics_rejects_removed_frontmatter_fields(workspace: Path) -> None:
    service = BaseService(WorkspaceSettings.load("test", workspace), BaseRepository())

    issues = service._semantic_issues(
        {
            "properties": {"lifecycle": {"displayName": "生命周期"}},
            "views": [
                {
                    "type": "table",
                    "name": "旧问题",
                    "filters": 'type == "issue" && lifecycle != "archived"',
                    "order": ["file.name", "lifecycle"],
                }
            ],
        },
        "旧视图.base",
    )

    assert issues == [
        {"code": "base-unknown-field", "path": "旧视图.base", "detail": "lifecycle"},
        {"code": "base-enum-value-invalid", "path": "旧视图.base", "detail": "type=issue"},
    ]
