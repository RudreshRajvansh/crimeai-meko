"""Semantic search over crime narratives with pgvector (cosine distance, HNSW index)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import Crime
from app.nlp.privacy.redaction import redact


def crime_document(crime_type: str, sub_type: str | None, description: str | None, district: str | None = None) -> str:
    """
    Text that represents a crime's modus operandi for embedding.

    Place names are deliberately excluded: location is compared geometrically,
    and naming the police station in the text would make identical MOs at two
    stations look less alike, which is the opposite of what cross-station
    linkage needs. PII is removed before the text reaches any model.
    """
    parts = [crime_type.replace("_", " ")]
    if sub_type:
        parts.append(sub_type)
    if description:
        parts.append(redact(description).text)
    return ". ".join(parts)


async def find_similar_crimes(
    db: AsyncSession,
    query_vector: list[float],
    top_k: int = 5,
    crime_type_filter: str | None = None,
    min_similarity: float = 0.5,
    exclude_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    distance = Crime.embedding.cosine_distance(query_vector)
    query = (
        select(
            Crime.id, Crime.crime_type, Crime.sub_type, Crime.description, Crime.district, Crime.city,
            Crime.severity, Crime.occurred_at, Crime.case_number, Crime.series_id,
            (1 - distance).label("similarity"),
        )
        .where(Crime.embedding.is_not(None), distance <= 1 - min_similarity)
        .order_by(distance)
        .limit(top_k)
    )
    if crime_type_filter:
        query = query.where(Crime.crime_type == crime_type_filter)
    if exclude_id:
        query = query.where(Crime.id != exclude_id)

    rows = (await db.execute(query)).all()
    return [
        {
            "id": str(row.id),
            "crime_type": row.crime_type,
            "sub_type": row.sub_type,
            "description": redact(row.description or "").text[:300],
            "district": row.district,
            "city": row.city,
            "severity": row.severity,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "case_number": row.case_number,
            "series_id": row.series_id,
            "similarity": round(float(row.similarity), 4),
        }
        for row in rows
    ]


async def crimes_missing_embeddings(db: AsyncSession, limit: int) -> list[Any]:
    rows = await db.execute(
        select(Crime.id, Crime.crime_type, Crime.sub_type, Crime.description, Crime.district)
        .where(Crime.embedding.is_(None))
        .order_by(Crime.occurred_at.desc())
        .limit(limit)
    )
    return list(rows.all())


async def store_embeddings(db: AsyncSession, vectors: dict[uuid.UUID, list[float]]) -> int:
    if not vectors:
        return 0
    await db.execute(update(Crime), [{"id": crime_id, "embedding": vector} for crime_id, vector in vectors.items()])
    return len(vectors)
