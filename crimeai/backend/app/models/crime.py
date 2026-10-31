"""Crime ORM model with PostGIS geometry and a pgvector embedding."""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class Crime(Base):
    __tablename__ = "crimes"

    crime_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sub_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[object] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="reported", index=True)
    case_number: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    assigned_officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    legal_sections: Mapped[list[str] | None] = mapped_column(ARRAY(String(30)), nullable=True)

    # Custody clock: BNSS s.187(3) default bail if no chargesheet within 60/90 days of remand.
    accused_arrested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The custody clock runs from the first remand order; the arrest date is only a fallback.
    accused_first_remanded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chargesheet_filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    series_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True, deferred=True)

    fir_report: Mapped[object | None] = relationship("FIRReport", back_populates="crime", uselist=False)
