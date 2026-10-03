"""Remove obsolete multi-stage Workspace adoption state."""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("adoption_batches")


def downgrade() -> None:
    raise RuntimeError("The adoption workflow consolidation is intentionally irreversible")
