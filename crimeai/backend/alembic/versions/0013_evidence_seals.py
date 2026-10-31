"""Chain of custody: seals of a case file's document and review hashes, anchored on Solana.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_seals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("crime_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merkle_root", sa.String(64), nullable=False),
        sa.Column("leaves", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("memo", sa.String(566), nullable=False),
        sa.Column("cluster", sa.String(20), nullable=False),
        sa.Column("signature", sa.String(100), nullable=True),
        sa.Column("slot", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sealed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["crime_id"], ["crimes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sealed_by"], ["users.id"], ondelete="SET NULL"),
    )
    # A case's seals newest first: hash on the case, range on the time.
    op.execute("CREATE INDEX ix_evidence_seals_crime_id ON evidence_seals (crime_id HASH, created_at DESC)"
               if _yugabyte() else "CREATE INDEX ix_evidence_seals_crime_id ON evidence_seals (crime_id, created_at DESC)")


def _yugabyte() -> bool:
    return "-YB-" in op.get_bind().execute(sa.text("SELECT version()")).scalar_one()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evidence_seals_crime_id")
    op.drop_table("evidence_seals")
