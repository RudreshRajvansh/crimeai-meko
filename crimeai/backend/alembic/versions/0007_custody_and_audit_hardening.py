"""First-remand date for the custody clock; audit log protected against TRUNCATE.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crimes", sa.Column("accused_first_remanded_at", sa.DateTime(timezone=True), nullable=True))
    # The row-level trigger from 0002 blocks UPDATE and DELETE, but TRUNCATE skips row triggers entirely.
    op.execute(
        "CREATE OR REPLACE FUNCTION audit_logs_no_truncate() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_block_truncate BEFORE TRUNCATE ON audit_logs "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_no_truncate()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_truncate ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_no_truncate()")
    op.drop_column("crimes", "accused_first_remanded_at")
