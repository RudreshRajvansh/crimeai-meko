"""
Model and output registry.

Workers write versioned artifacts to Postgres; the API reads them. Nothing ML
depends on a container's local disk, so API and worker can run on separate
machines, scale independently and survive redeploys. Every forecast carries
the version of the model that produced it, which is what makes a prediction
auditable after the fact.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any

import joblib
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_artifact import MLArtifact

HOTSPOT_MODEL = "hotspot_model"
HOTSPOT_FORECAST = "hotspot_forecast"
RISK_SCORES = "district_risk_scores"
CLUSTERS = "crime_clusters"
CRIME_SERIES = "crime_series"

_KEEP_VERSIONS = 10


@dataclass(frozen=True, slots=True)
class Artifact:
    name: str
    version: int
    content_type: str
    payload: bytes
    metadata: dict[str, Any]
    created_at: str

    def as_json(self) -> Any:
        return json.loads(self.payload)

    def as_object(self) -> Any:
        return joblib.load(io.BytesIO(self.payload))


async def _next_version(db: AsyncSession, name: str) -> int:
    current = await db.execute(select(func.max(MLArtifact.version)).where(MLArtifact.name == name))
    return (current.scalar_one() or 0) + 1


async def save_json(db: AsyncSession, name: str, data: Any, metadata: dict[str, Any] | None = None) -> int:
    return await _save(db, name, json.dumps(data, default=str).encode(), "application/json", metadata)


async def save_object(db: AsyncSession, name: str, obj: Any, metadata: dict[str, Any] | None = None) -> int:
    buffer = io.BytesIO()
    joblib.dump(obj, buffer, compress=3)
    return await _save(db, name, buffer.getvalue(), "application/x-joblib", metadata)


async def _save(db: AsyncSession, name: str, payload: bytes, content_type: str, metadata: dict[str, Any] | None) -> int:
    version = await _next_version(db, name)
    db.add(MLArtifact(name=name, version=version, content_type=content_type, payload=payload, meta=metadata or {}))
    await db.flush()
    stale = select(MLArtifact.id).where(MLArtifact.name == name).order_by(MLArtifact.version.desc()).offset(_KEEP_VERSIONS)
    await db.execute(delete(MLArtifact).where(MLArtifact.id.in_(stale)))
    return version


async def latest(db: AsyncSession, name: str) -> Artifact | None:
    row = (
        await db.execute(
            select(MLArtifact).where(MLArtifact.name == name).order_by(MLArtifact.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return Artifact(row.name, row.version, row.content_type, row.payload, row.meta or {}, row.created_at.isoformat())


async def history(db: AsyncSession, name: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(MLArtifact.version, MLArtifact.meta, MLArtifact.created_at)
        .where(MLArtifact.name == name)
        .order_by(MLArtifact.version.desc())
        .limit(limit)
    )
    return [{"version": v, "metadata": m, "created_at": c.isoformat()} for v, m, c in rows.all()]
