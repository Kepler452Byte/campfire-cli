"""Add Workspace folder adoption batches."""

import sqlalchemy as sa

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adoption_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(63),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_name", sa.String(128), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("staging_path", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("inventory_json", sa.Text(), nullable=False),
        sa.Column("plan_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "batch_name"),
    )
    op.create_index("ix_adoption_batches_workspace_id", "adoption_batches", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("adoption_batches")
