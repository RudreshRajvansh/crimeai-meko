"""Meko shared memory: call log, datapack ids, memories this agency wrote, cached exclusions.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
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
        "meko_calls",
        *_base(),
        sa.Column("run_id", sa.String(40), nullable=False),
        sa.Column("agent", sa.String(60), nullable=False),
        sa.Column("tool", sa.String(60), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("datapack", sa.String(40), nullable=True),
        sa.Column("transport", sa.String(10), nullable=False, server_default="mcp"),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False, server_default=""),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meko_calls_run_id", "meko_calls", ["run_id"])
    # Range (not hash) index: the live feed reads the newest calls first.
    op.execute("CREATE INDEX ix_meko_calls_created_at ON meko_calls (created_at DESC)")

    op.create_table(
        "meko_datapacks",
        *_base(),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("datapack_id", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_meko_datapacks_key"),
    )

    op.create_table(
        "meko_memories",
        *_base(),
        sa.Column("memory_id", sa.String(80), nullable=False),
        sa.Column("datapack", sa.String(40), nullable=False),
        sa.Column("agent", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("case_ref", sa.String(80), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meko_memories_memory_id", "meko_memories", ["memory_id"])
    op.create_index("ix_meko_memories_case_ref", "meko_memories", ["case_ref"])

    op.create_table(
        "meko_exclusions",
        *_base(),
        sa.Column("token", sa.String(20), nullable=False),
        sa.Column("memory_id", sa.String(80), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_meko_exclusions_token"),
    )


def downgrade() -> None:
    op.drop_table("meko_exclusions")
    op.drop_index("ix_meko_memories_case_ref", table_name="meko_memories")
    op.drop_index("ix_meko_memories_memory_id", table_name="meko_memories")
    op.drop_table("meko_memories")
    op.drop_table("meko_datapacks")
    op.execute("DROP INDEX IF EXISTS ix_meko_calls_created_at")
    op.drop_index("ix_meko_calls_run_id", table_name="meko_calls")
    op.drop_table("meko_calls")
