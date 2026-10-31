"""User ORM model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="readonly")
    badge_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved", server_default="approved", index=True)
    request_id: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    requested_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    fir_reports: Mapped[list] = relationship("FIRReport", back_populates="submitted_by_user", lazy="noload")
    audit_logs: Mapped[list] = relationship("AuditLog", back_populates="user", lazy="noload")
