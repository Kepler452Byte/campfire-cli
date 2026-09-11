from __future__ import annotations

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
