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
        connection.execute("create table workspaces (id varchar(63) primary key)")
        connection.execute(
            "create table documents ("
            "id integer primary key, workspace_id varchar(63) not null, path text not null, "
            "content_hash varchar(64) not null, document_type varchar(64), "
            'domain_id varchar(128), status varchar(32), "exists" boolean not null, '
            "indexed_at datetime not null, unique(workspace_id, path))"
        )

    upgrade_database(database)

    with sqlite3.connect(database) as connection:
        version = connection.execute("select version_num from alembic_version").fetchone()
        adoption_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'adoption_batches'"
        ).fetchone()
    assert version == ("011",)
    assert adoption_table is None

    with sqlite3.connect(database) as connection:
        document_columns = {
            row[1] for row in connection.execute("pragma table_info(documents)").fetchall()
        }
        edge_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'document_edges'"
        ).fetchone()
        state_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'document_index_state'"
        ).fetchone()
        state_columns = {
            row[1]
            for row in connection.execute("pragma table_info(document_index_state)").fetchall()
        }
    assert {"document_status", "task_status", "project_id", "source_mtime_ns"} <= document_columns
    assert {"topology_hash", "rebuilt_at"} <= state_columns
    assert edge_table == ("document_edges",)
    assert state_table == ("document_index_state",)
