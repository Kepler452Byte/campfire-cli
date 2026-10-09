"""Preserve legacy Project metadata as stable repository entries."""

import json

import sqlalchemy as sa

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if "projects" not in sa.inspect(connection).get_table_names():
        return
    op.add_column(
        "projects", sa.Column("repositories", sa.Text(), nullable=False, server_default="[]")
    )
    rows = list(
        connection.execute(
            sa.text("SELECT id, git_remote_url, local_path, default_branch FROM projects")
        ).mappings()
    )
    for row in rows:
        repositories = [
            {
                "id": "default",
                **{key: row[key] for key in ("git_remote_url", "local_path", "default_branch")},
            }
        ]
        connection.execute(
            sa.text("UPDATE projects SET repositories=:value WHERE id=:id"),
            {"value": json.dumps(repositories), "id": row["id"]},
        )

    with op.batch_alter_table("projects") as batch:
        for name in ("git_remote_url", "local_path", "default_branch"):
            batch.drop_column(name)


def downgrade() -> None:
    raise RuntimeError("Multiple repository bindings cannot be downgraded losslessly")
