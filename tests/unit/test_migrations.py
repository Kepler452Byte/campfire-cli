from __future__ import annotations

import sqlite3
from pathlib import Path

from campfire_cli.common.database import upgrade_database


def test_upgrade_removes_obsolete_adoption_batch_state(tmp_path: Path) -> None:
    database = tmp_path / "campfire.db"
    with sqlite3.connect(database) as connection:
        connection.execute("create table alembic_version (version_num varchar(32) not null)")
        connection.execute("insert into alembic_version values ('007')")
        connection.execute("create table adoption_batches (id integer primary key)")

    upgrade_database(database)

    with sqlite3.connect(database) as connection:
        version = connection.execute("select version_num from alembic_version").fetchone()
        adoption_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'adoption_batches'"
        ).fetchone()
    assert version == ("008",)
    assert adoption_table is None
