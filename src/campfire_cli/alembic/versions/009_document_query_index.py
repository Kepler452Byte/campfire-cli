"""Expand the rebuildable document query index."""

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("name", sa.String(240)))
        batch.add_column(sa.Column("project_id", sa.String(63)))
        batch.add_column(sa.Column("lifecycle", sa.String(32)))
        batch.add_column(sa.Column("priority", sa.String(32)))
        batch.add_column(sa.Column("assignee_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("due", sa.String(32)))
        batch.add_column(sa.Column("source_updated", sa.String(32)))
        batch.add_column(sa.Column("source_size", sa.Integer()))
        batch.add_column(sa.Column("source_mtime_ns", sa.Integer()))
        batch.add_column(
            sa.Column("queryable", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    op.create_table(
        "document_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(63),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text()),
        sa.Column("raw_target", sa.Text(), nullable=False),
        sa.Column("relation_type", sa.String(48), nullable=False),
        sa.Column("resolution", sa.String(24), nullable=False),
        sa.Column("candidates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("line", sa.Integer()),
    )
    op.create_index("ix_document_edges_workspace_id", "document_edges", ["workspace_id"])
    op.create_index("ix_document_edges_source_path", "document_edges", ["source_path"])
    op.create_index("ix_document_edges_target_path", "document_edges", ["target_path"])

    op.create_table(
        "document_index_state",
        sa.Column(
            "workspace_id",
            sa.String(63),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("topology_hash", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("rebuilt_at", sa.DateTime(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("document_index_state")
    op.drop_table("document_edges")
    with op.batch_alter_table("documents") as batch:
        for column in (
            "queryable",
            "source_mtime_ns",
            "source_size",
            "source_updated",
            "due",
            "assignee_json",
            "priority",
            "lifecycle",
            "project_id",
            "name",
        ):
            batch.drop_column(column)
