"""Link-analysis entities and mentions; FIR language column.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "key", name="uq_entities_kind_key"),
    )
    op.create_index("ix_entities_kind", "entities", ["kind"])
    op.create_index("ix_entities_case_count", "entities", ["case_count"])
    op.execute("CREATE INDEX ix_entities_label_trgm ON entities USING GIN (label gin_trgm_ops)")

    op.create_table(
        "entity_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crime_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fir_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="nlp"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crime_id"], ["crimes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fir_id"], ["fir_reports.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("entity_id", "crime_id", name="uq_entity_mentions_entity_crime"),
    )
    op.create_index("ix_entity_mentions_entity_id", "entity_mentions", ["entity_id"])
    op.create_index("ix_entity_mentions_crime_id", "entity_mentions", ["crime_id"])

    op.add_column("fir_reports", sa.Column("language", sa.String(10), nullable=True))
    op.create_index("ix_fir_reports_language", "fir_reports", ["language"])


def downgrade() -> None:
    op.drop_index("ix_fir_reports_language", table_name="fir_reports")
    op.drop_column("fir_reports", "language")
    op.drop_table("entity_mentions")
    op.execute("DROP INDEX IF EXISTS ix_entities_label_trgm")
    op.drop_table("entities")
