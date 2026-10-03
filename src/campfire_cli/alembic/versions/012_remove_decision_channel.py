"""Remove the obsolete SQLite Decision workflow."""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS decision_events")
    op.execute("DROP TABLE IF EXISTS decisions")


def downgrade() -> None:
    raise RuntimeError("The retired Decision workflow is intentionally not restored")
