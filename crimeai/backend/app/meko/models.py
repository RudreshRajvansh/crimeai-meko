"""Local bookkeeping for Meko, stored in YugabyteDB: the call log, datapack ids, what we wrote, exclusions."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MekoCall(Base):
    """Every Meko call this deployment made: the evidence behind everything the UI shows as context."""

    __tablename__ = "meko_calls"

    run_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(60), nullable=False)
    tool: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    datapack: Mapped[str | None] = mapped_column(String(40), nullable=True)
    transport: Mapped[str] = mapped_column(String(10), nullable=False, default="mcp")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)


class MekoDatapack(Base):
    __tablename__ = "meko_datapacks"

    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    datapack_id: Mapped[str] = mapped_column(String(80), nullable=False)


class MekoMemory(Base):
    """A memory this deployment wrote, so corrections and forgets can pass the writer's agent_id."""

    __tablename__ = "meko_memories"

    memory_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    datapack: Mapped[str] = mapped_column(String(40), nullable=False)
    agent: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    case_ref: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class MekoExclusion(Base):
    """
    Promoted grid knowledge that an identifier is not a suspect's (a public helpline, for example), cached
    locally so link alerts can honour it without a network call. Filled from what Meko returns.
    """

    __tablename__ = "meko_exclusions"

    token: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    memory_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
