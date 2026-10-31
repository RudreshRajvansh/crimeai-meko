"""
Pydantic schemas for Crime endpoints.
Separate schemas for: Create, Update, Response, List, GeoJSON.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CrimeStatus = Literal["reported", "under_investigation", "resolved", "closed"]
CrimeSeverity = Literal[1, 2, 3, 4, 5]

VALID_CRIME_TYPES = {
    "theft", "assault", "robbery", "fraud", "drug_offense",
    "vandalism", "trespass", "murder", "kidnapping", "cybercrime",
    "sexual_offense", "arson", "traffic_violation", "extortion", "other",
    "burglary", "vehicle_theft", "chain_snatching", "domestic_violence",
}

class CrimeCreateRequest(BaseModel):
    crime_type: str = Field(..., min_length=2, max_length=100)
    sub_type: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=5000)
    severity: int = Field(default=1, ge=1, le=5)

    # Location (required)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_name: str | None = Field(None, max_length=255)
    address: str | None = Field(None, max_length=500)
    district: str | None = Field(None, max_length=100)
    city: str = Field(..., min_length=2, max_length=100)

    # Temporal
    occurred_at: datetime

    status: CrimeStatus = "reported"
    case_number: str | None = Field(None, max_length=50)
    assigned_officer_id: uuid.UUID | None = None
    legal_sections: list[str] | None = Field(None, max_length=20)
    accused_arrested_at: datetime | None = None

    # Weapon / suspect info (stored in description; extracted by NLP)
    weapon_used: str | None = Field(None, max_length=100)
    num_suspects: int | None = Field(None, ge=0, le=100)

    @field_validator("crime_type")
    @classmethod
    def validate_crime_type(cls, v: str) -> str:
        normalized = v.lower().strip().replace(" ", "_")
        if normalized not in VALID_CRIME_TYPES:
            raise ValueError(f"crime_type must be one of {sorted(VALID_CRIME_TYPES)}")
        return normalized

    @field_validator("occurred_at", "accused_arrested_at")
    @classmethod
    def not_in_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        if v > datetime.now(UTC):
            raise ValueError("timestamp cannot be in the future")
        return v


class CrimeUpdateRequest(BaseModel):
    """All fields optional — PATCH semantics."""
    crime_type: str | None = Field(None, min_length=2, max_length=100)
    sub_type: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=5000)
    severity: int | None = Field(None, ge=1, le=5)
    location_name: str | None = Field(None, max_length=255)
    address: str | None = Field(None, max_length=500)
    district: str | None = Field(None, max_length=100)
    city: str | None = Field(None, min_length=2, max_length=100)
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    occurred_at: datetime | None = None
    status: CrimeStatus | None = None
    case_number: str | None = Field(None, max_length=50)
    assigned_officer_id: uuid.UUID | None = None
    legal_sections: list[str] | None = Field(None, max_length=20)
    accused_arrested_at: datetime | None = None
    chargesheet_filed_at: datetime | None = None

    @model_validator(mode="after")
    def lat_lng_both_or_neither(self) -> CrimeUpdateRequest:
        has_lat = self.latitude is not None
        has_lng = self.longitude is not None
        if has_lat != has_lng:
            raise ValueError("latitude and longitude must both be provided together")
        return self


class CrimeFilterParams(BaseModel):
    """Query parameters for listing crimes."""
    crime_type: str | None = None
    district: str | None = None
    city: str | None = None
    status: CrimeStatus | None = None
    severity_min: int | None = Field(None, ge=1, le=5)
    severity_max: int | None = Field(None, ge=1, le=5)
    from_date: datetime | None = None
    to_date: datetime | None = None
    assigned_officer_id: uuid.UUID | None = None
    cluster_id: int | None = None
    series_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class NearbyFilterParams(BaseModel):
    """Query parameters for geo radius search."""
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_km: float = Field(default=2.0, ge=0.1, le=50.0)
    crime_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)

class CrimeResponse(BaseModel):
    id: uuid.UUID
    crime_type: str
    sub_type: str | None
    description: str | None
    severity: int
    location_name: str | None
    address: str | None
    district: str | None
    city: str
    latitude: float
    longitude: float
    occurred_at: datetime
    reported_at: datetime
    status: str
    case_number: str | None
    assigned_officer_id: uuid.UUID | None
    legal_sections: list[str] | None = None
    accused_arrested_at: datetime | None = None
    chargesheet_filed_at: datetime | None = None
    cluster_id: int | None
    series_id: str | None = None
    risk_score: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrimeListResponse(BaseModel):
    items: list[CrimeResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class CrimeSummaryResponse(BaseModel):
    """Lightweight version for map markers — no heavy fields."""
    id: uuid.UUID
    crime_type: str
    severity: int
    latitude: float
    longitude: float
    district: str | None
    status: str
    occurred_at: datetime
    risk_score: float | None

    model_config = {"from_attributes": True}


class CrimeStatsResponse(BaseModel):
    """Aggregated statistics for the dashboard."""
    total_crimes: int
    by_type: dict[str, int]
    by_district: dict[str, int]
    by_status: dict[str, int]
    by_severity: dict[str, int]
    by_month: list[dict[str, Any]]
    avg_daily_crimes: float
    most_active_hour: int

class GeoJSONPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: list[float]  # [longitude, latitude]


class GeoJSONFeatureProperties(BaseModel):
    id: str
    crime_type: str
    sub_type: str | None
    severity: int
    district: str | None
    city: str
    status: str
    occurred_at: str
    case_number: str | None
    risk_score: float | None


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONPoint
    properties: GeoJSONFeatureProperties


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]
    metadata: dict[str, Any] = {}
