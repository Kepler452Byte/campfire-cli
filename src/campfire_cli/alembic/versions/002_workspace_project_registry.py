"""Create the SQLite-backed Workspace and Project registry."""

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False, unique=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_workspaces_is_default", "workspaces", ["is_default"])
    op.create_table(
        "projects",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(63),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("document_domain", sa.Text(), nullable=False),
        sa.Column("git_remote_url", sa.Text()),
        sa.Column("local_path", sa.Text()),
        sa.Column("default_branch", sa.String(160)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("projects")
    op.drop_table("workspaces")
