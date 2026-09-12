"""Rename the former migration persistence model to Workspace restructure."""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("migration_batches", "restructure_batches")
    op.rename_table("migration_items", "restructure_items")
    op.drop_index("ix_migration_batches_workspace_id", table_name="restructure_batches")
    op.drop_index("ix_migration_items_workspace_id", table_name="restructure_items")
    op.drop_index("ix_migration_items_batch_id", table_name="restructure_items")
    op.create_index("ix_restructure_batches_workspace_id", "restructure_batches", ["workspace_id"])
    op.create_index("ix_restructure_items_workspace_id", "restructure_items", ["workspace_id"])
    op.create_index("ix_restructure_items_batch_id", "restructure_items", ["batch_id"])


def downgrade() -> None:
    raise RuntimeError("The Workspace restructure rename is intentionally irreversible")
