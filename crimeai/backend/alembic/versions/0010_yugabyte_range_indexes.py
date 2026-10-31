"""YugabyteDB range indexes for time-ordered reads.

YugabyteDB shards a plain index by HASH of its first column, which suits equality lookups but cannot serve
"since a date, newest first" scans. The feeds and dashboards read exactly that way, so these indexes become
range (DESC/ASC) indexes, and the district/date index keeps district as the hash key with time ranged inside.
Skipped on plain PostgreSQL, where btree indexes are already ordered.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_crimes_occurred_at", "crimes", "(occurred_at DESC)", "(occurred_at)", ""),
    ("ix_crimes_district_occurred_at", "crimes", "(district HASH, occurred_at DESC)", "(district, occurred_at)", ""),
    ("ix_crimes_open_custody", "crimes", "(accused_arrested_at ASC)", "(accused_arrested_at)",
     " WHERE accused_arrested_at IS NOT NULL AND chargesheet_filed_at IS NULL"),
    ("ix_alerts_created_at", "alerts", "(created_at DESC)", "(created_at)", ""),
    ("ix_audit_logs_created_at", "audit_logs", "(created_at DESC)", "(created_at)", ""),
    ("ix_entities_case_count", "entities", "(case_count DESC)", "(case_count)", ""),
]


def _yugabyte() -> bool:
    return "-YB-" in op.get_bind().execute(sa.text("SELECT version()")).scalar_one()


def _rebuild(columns_index: int) -> None:
    for name, table, *columns, where in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
        op.execute(f"CREATE INDEX {name} ON {table} {columns[columns_index]}{where}")


def upgrade() -> None:
    if _yugabyte():
        _rebuild(0)


def downgrade() -> None:
    if _yugabyte():
        _rebuild(1)
