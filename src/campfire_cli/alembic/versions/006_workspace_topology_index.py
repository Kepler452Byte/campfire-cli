"""Add rebuildable Space and Domain topology indexes."""

import sqlalchemy as sa

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def workspace_column() -> sa.Column:
    return sa.Column(
        "workspace_id",
        sa.String(63),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "spaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        workspace_column(),
        sa.Column("space_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("space_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "space_id"),
    )
    op.create_index("ix_spaces_workspace_id", "spaces", ["workspace_id"])
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), primary_key=True),
        workspace_column(),
        sa.Column("domain_id", sa.String(128), nullable=False),
        sa.Column("space_id", sa.String(128), nullable=False),
        sa.Column("parent_domain_id", sa.String(128)),
        sa.Column("project_id", sa.String(63)),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("domain_type", sa.String(64), nullable=False),
        sa.Column("governance", sa.String(64), nullable=False),
        sa.Column("moc", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "domain_id"),
    )
    op.create_index("ix_domains_workspace_id", "domains", ["workspace_id"])
    op.create_index("ix_domains_space_id", "domains", ["space_id"])


def downgrade() -> None:
    op.drop_table("domains")
    op.drop_table("spaces")
