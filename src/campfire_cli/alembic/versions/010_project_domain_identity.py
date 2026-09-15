"""Store the stable project root Domain identity.

Revision ID: 010_project_domain_identity
Revises: 009_document_query_index
"""

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if "projects" not in sa.inspect(connection).get_table_names():
        return
    with op.batch_alter_table("projects") as batch:
        batch.alter_column(
            "document_domain",
            new_column_name="document_domain_id",
            existing_type=sa.Text(),
            type_=sa.String(length=128),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.alter_column(
            "document_domain_id",
            new_column_name="document_domain",
            existing_type=sa.String(length=128),
            type_=sa.Text(),
            existing_nullable=False,
        )
