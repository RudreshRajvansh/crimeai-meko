"""Profile change requests: the updated_at column every model inherits from Base.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_change_requests",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_profile_change_requests_user_id", "profile_change_requests", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_change_requests_user_id", table_name="profile_change_requests")
    op.drop_column("profile_change_requests", "updated_at")
