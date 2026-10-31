"""Initial schema: users, crimes, fir_reports, alerts, audit_logs, PostGIS, pgvector

Revision ID: 0001
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")    # fuzzy text search
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="police"),
        sa.Column("badge_number", sa.String(20), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_badge_number", "users", ["badge_number"])

    # ── crimes ────────────────────────────────────────────────────────────────
    op.create_table(
        "crimes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("crime_type", sa.String(100), nullable=False),
        sa.Column("sub_type", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("location_name", sa.String(255), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geom", geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="reported"),
        sa.Column("case_number", sa.String(50), nullable=True),
        sa.Column("assigned_officer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cluster_id", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        # pgvector embedding (384-dim for sentence-transformers/all-MiniLM-L6-v2)
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crimes_crime_type", "crimes", ["crime_type"])
    op.create_index("ix_crimes_district", "crimes", ["district"])
    op.create_index("ix_crimes_city", "crimes", ["city"])
    op.create_index("ix_crimes_occurred_at", "crimes", ["occurred_at"])
    op.create_index("ix_crimes_status", "crimes", ["status"])
    op.create_index("ix_crimes_case_number", "crimes", ["case_number"], unique=True)
    op.create_index("ix_crimes_cluster_id", "crimes", ["cluster_id"])
    # Spatial index (GIST) for PostGIS queries
    op.execute("CREATE INDEX ix_crimes_geom ON crimes USING GIST (geom)")
    # Trigram index for description full-text search
    op.execute("CREATE INDEX ix_crimes_description_trgm ON crimes USING GIN (description gin_trgm_ops)")

    # ── fir_reports ───────────────────────────────────────────────────────────
    op.create_table(
        "fir_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fir_number", sa.String(50), nullable=False),
        sa.Column("crime_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("extracted_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("nlp_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["crime_id"], ["crimes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_fir_reports_fir_number", "fir_reports", ["fir_number"], unique=True)
    op.create_index("ix_fir_reports_nlp_status", "fir_reports", ["nlp_status"])

    # ── alerts ────────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("related_crime_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_cluster_id", sa.Integer(), nullable=True),
        sa.Column("target_role", sa.String(20), nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_is_resolved", "alerts", ["is_resolved"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("request_id", sa.String(50), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ── Updated_at auto-trigger ───────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    for table in ["users", "crimes", "fir_reports", "alerts", "audit_logs"]:
        op.execute(f"""
            CREATE TRIGGER trigger_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    for table in ["users", "crimes", "fir_reports", "alerts", "audit_logs"]:
        op.execute(f"DROP TRIGGER IF EXISTS trigger_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.drop_table("audit_logs")
    op.drop_table("alerts")
    op.drop_table("fir_reports")
    op.drop_table("crimes")
    op.drop_table("users")
