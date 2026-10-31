"""Role an applicant asked for on the access-request form.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("requested_role", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "requested_role")
