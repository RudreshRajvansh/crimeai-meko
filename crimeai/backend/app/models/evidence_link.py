"""Reference to an e-Sakshya recording held by the state's evidence platform; CrimeAI never stores the media."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (UniqueConstraint("crime_id", "sid", name="uq_evidence_links_crime_sid"),)

    crime_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crimes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # e-Sakshya session id (16 digits under the notified state rules) and the platform's hash of the packet.
    sid: Mapped[str] = mapped_column(String(32), nullable=False)
    packet_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # BNSS provision the recording satisfies, e.g. "105" (search and seizure) or "176" (crime scene).
    provision: Mapped[str] = mapped_column(String(10), nullable=False, default="105")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    linked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
