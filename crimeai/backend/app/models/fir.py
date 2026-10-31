"""FIR (First Information Report) ORM model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FIRReport(Base):
    __tablename__ = "fir_reports"

    fir_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    crime_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crimes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    incident_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # SHA-256 of the uploaded original: proves the document has not changed since intake.
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    extracted_entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # pending -> processing -> completed | failed | awaiting_ocr
    nlp_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    nlp_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    nlp_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    crime: Mapped[object | None] = relationship("Crime", back_populates="fir_report")
    submitted_by_user: Mapped[object] = relationship("User", back_populates="fir_reports", foreign_keys=[submitted_by])
