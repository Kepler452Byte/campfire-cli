"""Add persistent Decision state and append-only events."""

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(63),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("related_documents_json", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(160)),
        sa.Column("session_provider", sa.String(64)),
        sa.Column("session_id", sa.String(200)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("answered_by", sa.String(160)),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("answered_at", sa.DateTime()),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("workspace_id", "dedupe_key"),
    )
    op.create_index("ix_decisions_workspace_id", "decisions", ["workspace_id"])
    op.create_index("ix_decisions_status", "decisions", ["status"])
    op.create_table(
        "decision_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(63),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "decision_id",
            sa.String(36),
            sa.ForeignKey("decisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(160)),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_decision_events_workspace_id", "decision_events", ["workspace_id"])
    op.create_index("ix_decision_events_decision_id", "decision_events", ["decision_id"])
    op.create_index("ix_decision_events_event_type", "decision_events", ["event_type"])


def downgrade() -> None:
    raise RuntimeError("Decision history is intentionally irreversible")
