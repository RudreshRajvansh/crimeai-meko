"""e-Sakshya evidence references per case.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("crime_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crimes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sid", sa.String(32), nullable=False),
        sa.Column("packet_hash", sa.String(128), nullable=True),
        sa.Column("provision", sa.String(10), nullable=False, server_default="105"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("crime_id", "sid", name="uq_evidence_links_crime_sid"),
    )
    op.create_index("ix_evidence_links_id", "evidence_links", ["id"])
    op.create_index("ix_evidence_links_crime_id", "evidence_links", ["crime_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_links_crime_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_id", table_name="evidence_links")
    op.drop_table("evidence_links")
