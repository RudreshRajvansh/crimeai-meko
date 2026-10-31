"""Versioned ML artifacts (models, forecasts, risk maps) shared by API and workers."""
from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MLArtifact(Base):
    __tablename__ = "ml_artifacts"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_ml_artifacts_name_version"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
