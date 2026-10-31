"""Case documents beyond the FIR, and the findings the investigation agents raise from them."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DOCUMENT_TYPES = {
    "fir": "FIR",
    "witness_statement": "Witness statement",
    "investigation_report": "Investigation report",
    "forensic_report": "Forensic report",
    "cctv_note": "CCTV description",
    "seizure_memo": "Seizure memo",
    "bank_statement": "Bank or UPI statement",
    "chargesheet": "Charge sheet",
    "court_document": "Court document",
}
REVIEW_STATUSES = ("open", "accepted", "rejected", "needs_investigation")


class CaseDocument(Base):
    """A statement, report or memo on a case. Only redacted text is stored; the original stays with the case file."""

    __tablename__ = "case_documents"

    crime_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crimes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class InvestigationFinding(Base):
    """A contradiction or gap an agent found, with every claim's source; an officer accepts, rejects or escalates it."""

    __tablename__ = "investigation_findings"
    __table_args__ = (UniqueConstraint("crime_id", "fingerprint", name="uq_investigation_findings_crime_fingerprint"),)

    crime_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crimes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # Stable key of what was found, so re-running the agents keeps an officer's review instead of duplicating it.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
