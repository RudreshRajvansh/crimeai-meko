"""Seals of a case file on Solana: the hashes of its documents and reviews, anchored as one Merkle root."""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceSeal(Base):
    """
    One seal: every leaf (a document or an officer's review) with its SHA-256, the Merkle root of the leaves, and
    the Solana transaction whose memo carries that root. Only hashes go on chain; the text stays in YugabyteDB.
    """

    __tablename__ = "evidence_seals"

    crime_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crimes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    leaves: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    memo: Mapped[str] = mapped_column(String(566), nullable=False)
    cluster: Mapped[str] = mapped_column(String(20), nullable=False)
    signature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # anchored (confirmed on chain), submitted (sent, not yet confirmed) or failed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sealed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
