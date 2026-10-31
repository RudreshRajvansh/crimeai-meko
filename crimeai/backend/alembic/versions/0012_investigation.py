"""Investigation intelligence: case documents and reviewable findings (contradictions, timeline gaps).

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "case_documents",
        *_base(),
        sa.Column("crime_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.String(120), nullable=True),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["crime_id"], ["crimes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="SET NULL"),
    )
    # One case's documents in recorded order: hash on the case, range on the date.
    op.execute("CREATE INDEX ix_case_documents_crime_id ON case_documents (crime_id HASH, recorded_at ASC)"
               if _yugabyte() else "CREATE INDEX ix_case_documents_crime_id ON case_documents (crime_id, recorded_at)")

    op.create_table(
        "investigation_findings",
        *_base(),
        sa.Column("crime_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["crime_id"], ["crimes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("crime_id", "fingerprint", name="uq_investigation_findings_crime_fingerprint"),
    )
    op.create_index("ix_investigation_findings_crime_id", "investigation_findings", ["crime_id"])
    op.create_index("ix_investigation_findings_status", "investigation_findings", ["status"])


def _yugabyte() -> bool:
    return "-YB-" in op.get_bind().execute(sa.text("SELECT version()")).scalar_one()


def downgrade() -> None:
    op.drop_index("ix_investigation_findings_status", table_name="investigation_findings")
    op.drop_index("ix_investigation_findings_crime_id", table_name="investigation_findings")
    op.drop_table("investigation_findings")
    op.execute("DROP INDEX IF EXISTS ix_case_documents_crime_id")
    op.drop_table("case_documents")
