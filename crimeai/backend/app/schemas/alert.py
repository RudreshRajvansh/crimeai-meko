"""Schemas for alerts."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.security import UserRole

AlertSeverity = Literal["low", "medium", "high", "critical"]
AlertType = Literal[
    "hotspot", "cluster", "high_risk", "pattern", "crime_series", "custody_deadline", "system", "manual",
]


class AlertCreateRequest(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    message: str = Field(..., min_length=10, max_length=2000)
    alert_type: AlertType = "manual"
    severity: AlertSeverity = "medium"
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    district: str | None = Field(None, max_length=100)
    related_crime_id: uuid.UUID | None = None
    target_role: UserRole | None = None
    assigned_to: uuid.UUID | None = None


class LinkedCase(BaseModel):
    id: uuid.UUID
    case_number: str | None
    crime_type: str
    district: str | None
    occurred_at: datetime | None


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message: str
    alert_type: str
    severity: str
    is_read: bool
    is_resolved: bool
    resolved_at: datetime | None = None
    latitude: float | None
    longitude: float | None
    district: str | None
    related_crime_id: uuid.UUID | None
    target_role: str | None
    assigned_to: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    # The cases behind the alert, and the link-graph node that shows them together.
    cases: list[LinkedCase] = Field(default_factory=list)
    graph_node: str | None = None
    entity_kind: str | None = None


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    unread_count: int
