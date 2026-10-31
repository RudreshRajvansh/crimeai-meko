"""Session revocation, pgvector column, model registry, FIR processing state, custody clock, crime series, append-only audit.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    # users: token versioning for revocation, typed last-login
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET last_login_at = last_login::timestamptz WHERE last_login IS NOT NULL")
    op.drop_column("users", "last_login")
    op.alter_column("users", "role", server_default="readonly")

    # crimes: real vector column, legal sections, custody clock, series linkage
    op.execute(f"ALTER TABLE crimes ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) USING embedding::vector({EMBEDDING_DIM})")
    op.add_column("crimes", sa.Column("legal_sections", postgresql.ARRAY(sa.String(30)), nullable=True))
    op.add_column("crimes", sa.Column("accused_arrested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crimes", sa.Column("chargesheet_filed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crimes", sa.Column("series_id", sa.String(40), nullable=True))
    op.create_index("ix_crimes_series_id", "crimes", ["series_id"])
    op.create_index("ix_crimes_assigned_officer_id", "crimes", ["assigned_officer_id"])
    op.create_index(
        "ix_crimes_open_custody", "crimes", ["accused_arrested_at"],
        postgresql_where=sa.text("accused_arrested_at IS NOT NULL AND chargesheet_filed_at IS NULL"),
    )
    op.execute("CREATE INDEX ix_crimes_geog ON crimes USING GIST ((geom::geography))")
    op.execute(
        "CREATE INDEX ix_crimes_embedding_hnsw ON crimes USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.create_index("ix_crimes_district_occurred_at", "crimes", ["district", "occurred_at"])

    # fir_reports: intake metadata and an explicit processing state machine
    op.add_column("fir_reports", sa.Column("incident_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fir_reports", sa.Column("redacted_text", sa.Text(), nullable=True))
    op.add_column("fir_reports", sa.Column("file_sha256", sa.String(64), nullable=True))
    op.add_column("fir_reports", sa.Column("nlp_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("fir_reports", sa.Column("nlp_error", sa.Text(), nullable=True))
    op.add_column("fir_reports", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("fir_reports", "file_type", type_=sa.String(50))
    op.create_index("ix_fir_reports_file_sha256", "fir_reports", ["file_sha256"])
    op.create_index("ix_fir_reports_crime_id", "fir_reports", ["crime_id"])

    # alerts: who resolved what, and a key for de-duplicating automated alerts
    op.add_column("alerts", sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("alerts", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("dedupe_key", sa.String(200), nullable=True))
    op.create_index("ix_alerts_dedupe_key", "alerts", ["dedupe_key"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    # ml_artifacts: versioned models and outputs shared by API and workers
    op.create_table(
        "ml_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_ml_artifacts_name_version"),
    )
    op.create_index("ix_ml_artifacts_name", "ml_artifacts", ["name"])

    # audit_logs: append-only. Evidence of access must not be editable, even by the application.
    op.execute("DROP TRIGGER IF EXISTS trigger_audit_logs_updated_at ON audit_logs")
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_audit_mutation() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION forbid_audit_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS forbid_audit_mutation()")
    op.drop_table("ml_artifacts")

    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_dedupe_key", table_name="alerts")
    for column in ("dedupe_key", "resolved_at", "resolved_by"):
        op.drop_column("alerts", column)

    op.drop_index("ix_fir_reports_crime_id", table_name="fir_reports")
    op.drop_index("ix_fir_reports_file_sha256", table_name="fir_reports")
    for column in ("processing_started_at", "nlp_error", "nlp_attempts", "file_sha256", "redacted_text", "incident_date"):
        op.drop_column("fir_reports", column)

    op.drop_index("ix_crimes_district_occurred_at", table_name="crimes")
    op.execute("DROP INDEX IF EXISTS ix_crimes_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_crimes_geog")
    op.drop_index("ix_crimes_open_custody", table_name="crimes")
    op.drop_index("ix_crimes_assigned_officer_id", table_name="crimes")
    op.drop_index("ix_crimes_series_id", table_name="crimes")
    for column in ("series_id", "chargesheet_filed_at", "accused_arrested_at", "legal_sections"):
        op.drop_column("crimes", column)
    op.execute("ALTER TABLE crimes ALTER COLUMN embedding TYPE double precision[] USING embedding::real[]")

    op.alter_column("users", "role", server_default="police")
    op.add_column("users", sa.Column("last_login", sa.String(50), nullable=True))
    op.execute("UPDATE users SET last_login = last_login_at::text WHERE last_login_at IS NOT NULL")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "token_version")
