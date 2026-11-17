from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect

from campfire_cli.common.database import create_sqlite_engine, initialize_database
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer


@pytest.mark.parametrize("change", ["old-column", "missing-column", "missing-table", "corrupt"])
def test_incompatible_cache_rebuilds_without_backups(workspace: Path, change: str) -> None:
    root = campfire_home()
    db = root / "campfire.db"
    engine = create_sqlite_engine(db)
    initialize_database(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO workspaces (id) VALUES ('obsolete')")
    if change == "corrupt":
        db.write_bytes(b"not a sqlite database")
    else:
        with sqlite3.connect(db) as connection:
            connection.execute(
                {
                    "old-column": "ALTER TABLE domains ADD COLUMN governance TEXT NOT NULL",
                    "missing-column": "ALTER TABLE documents DROP COLUMN priority",
                    "missing-table": "DROP TABLE document_edges",
                }[change]
            )
    facts = {p: p.read_bytes() for p in workspace.rglob("*.md")}
    facts.update(
        {
            workspace / ".campfire.yaml": (workspace / ".campfire.yaml").read_bytes(),
            root / "local.yaml": (root / "local.yaml").read_bytes(),
        }
    )
    files = set(root.iterdir())
    initialize_database(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM workspaces").scalar_one() == 0
        assert "governance" not in {c["name"] for c in inspect(connection).get_columns("domains")}
        assert "priority" in {c["name"] for c in inspect(connection).get_columns("documents")}
    assert all(p.read_bytes() == content for p, content in facts.items())
    assert set(root.iterdir()) - files <= {Path(str(db) + "-wal"), Path(str(db) + "-shm")}
    # A healthy cache is preserved rather than recreated on the next startup.
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO workspaces (id) VALUES ('preserved')")
    initialize_database(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT id FROM workspaces").scalar_one() == "preserved"
    engine.dispose()


def test_cache_replacement_refuses_active_connections(workspace: Path) -> None:
    db = campfire_home() / "campfire.db"
    engine = create_sqlite_engine(db)
    initialize_database(engine)
    with sqlite3.connect(db) as connection:
        connection.execute("ALTER TABLE domains ADD COLUMN obsolete TEXT")
    other = create_sqlite_engine(db)
    with other.connect():
        before = db.read_bytes()
        with pytest.raises(GovernanceBlockedError) as error:
            initialize_database(engine)
        assert error.value.code == "database-busy"
        assert db.read_bytes() == before
    initialize_database(engine)
    with engine.connect() as connection:
        assert "obsolete" not in {c["name"] for c in inspect(connection).get_columns("domains")}
    other.dispose()
    engine.dispose()


def test_rebuild_discards_old_plan_approval(workspace: Path) -> None:
    container = AppContainer.build("test")
    repository = container.restructure._repository
    repository.save_batch("uuid", "old", ".", "hash")
    repository._session.close()
    db = campfire_home() / "campfire.db"
    with sqlite3.connect(db) as connection:
        connection.execute("ALTER TABLE domains ADD COLUMN obsolete TEXT")
    replacement = AppContainer.build("test")
    with pytest.raises(ValueError, match="批次不存在"):
        replacement.restructure._repository.load_plan("old")
    assert replacement.document.list().status == "ok"


def test_healthy_cache_accepts_multiple_live_connections(workspace: Path) -> None:
    engine = create_sqlite_engine(campfire_home() / "campfire.db")
    initialize_database(engine)
    with engine.connect() as first, engine.connect() as second:
        assert first.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert second.exec_driver_sql("SELECT 1").scalar_one() == 1
        initialize_database(engine)
    engine.dispose()
