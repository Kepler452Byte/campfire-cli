"""Create Campfire state tables."""

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("document_type", sa.String(64)),
        sa.Column("domain_id", sa.String(128)),
        sa.Column("status", sa.String(32)),
        sa.Column("exists", sa.Boolean(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("path"),
    )
    op.create_index("ix_documents_path", "documents", ["path"])
    op.create_table(
        "governance_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("code", sa.String(96), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.UniqueConstraint("path", "code", "detail"),
    )
    op.create_index("ix_governance_issues_code", "governance_issues", ["code"])
    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("scanned_count", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
    )
    op.create_table(
        "migration_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("batch_name", sa.String(128), nullable=False, unique=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "migration_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("migration_batches.id"), nullable=False),
        sa.Column("item_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("proposed_type", sa.String(64)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("execution_status", sa.String(24), nullable=False),
    )
    op.create_index("ix_migration_items_batch_id", "migration_items", ["batch_id"])


def downgrade() -> None:
    op.drop_table("migration_items")
    op.drop_table("migration_batches")
    op.drop_table("maintenance_runs")
    op.drop_table("governance_issues")
    op.drop_table("documents")
