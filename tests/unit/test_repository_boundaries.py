from __future__ import annotations

import ast
from pathlib import Path


def test_repositories_do_not_create_business_identity_time_or_reports() -> None:
    project_root = Path(__file__).parents[2]
    repository_root = project_root / "src" / "campfire_cli" / "app"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in repository_root.glob("*/repository/*.py")
    )
    forbidden = ("uuid4", "datetime.now", "render_json_report", "render_maintenance_report")
    for symbol in forbidden:
        assert symbol not in sources


def test_workspace_services_do_not_depend_on_maintenance_services() -> None:
    project_root = Path(__file__).parents[2]
    services = project_root / "src/campfire_cli/app/workspace/service"
    forbidden_prefix = "campfire_cli.app.maintenance"
    violations: list[str] = []
    for path in services.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                forbidden_prefix
            ):
                violations.append(f"{path.name}:{node.lineno}:{node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefix):
                        violations.append(f"{path.name}:{node.lineno}:{alias.name}")
    assert violations == []
