"""Replace ambiguous document index state columns.

The document index is rebuildable, so historical values are intentionally
discarded instead of translated from the removed Frontmatter contract.
"""

import sqlalchemy as sa

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.alter_column(
            "status",
            new_column_name="document_status",
            existing_type=sa.String(length=32),
            existing_nullable=True,
        )
        batch.add_column(sa.Column("task_status", sa.String(32)))
    op.execute("DELETE FROM document_edges")
    op.execute("DELETE FROM documents")
    op.execute("DELETE FROM document_index_state")


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("task_status")
        batch.alter_column(
            "document_status",
            new_column_name="status",
            existing_type=sa.String(length=32),
            existing_nullable=True,
        )
