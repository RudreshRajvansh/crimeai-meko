"""Aggregates that power the visual analytics: temporal heat grid, language mix, time-lapse, global search."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.v1.dependencies.auth import Analyst, Viewer
from app.core.config import settings
from app.db.redis import CacheManager, get_redis
from app.db.session import get_db
from app.ml.similarity.embeddings import embed_text
from app.models.crime import Crime
from app.models.fir import FIRReport
from app.nlp.lexicons import LANGUAGES
from app.nlp.multilingual import analyse
from app.services import entity_graph

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


@router.get("/temporal-matrix", summary="Incidents by weekday x hour (local time)")
async def temporal_matrix(
    user: Viewer,
    db: DbDep,
    redis: RedisDep,
    days: int = Query(365, ge=7, le=1095),
    crime_type: str | None = None,
    district: str | None = None,
) -> dict:
    cache = CacheManager(redis, namespace="analytics")
    key = f"matrix:{days}:{crime_type}:{district}"
    if cached := await cache.get(key):
        return cached
    local = func.timezone(literal_column(f"'{settings.APP_TIMEZONE}'"), Crime.occurred_at)
    dow = func.extract("isodow", local)
    hour = func.extract("hour", local)
    query = select(dow.label("dow"), hour.label("hour"), func.count(Crime.id).label("n")).where(
        Crime.occurred_at >= datetime.now(UTC) - timedelta(days=days)
    )
    if crime_type:
        query = query.where(Crime.crime_type == crime_type)
    if district:
        query = query.where(Crime.district == district)
    rows = (await db.execute(query.group_by(dow, hour))).all()
    matrix = [[0] * 24 for _ in range(7)]
    for r in rows:
        matrix[int(r.dow) - 1][int(r.hour)] = r.n
    flat = [n for row in matrix for n in row]
    peak = max(flat) if flat else 0
    peak_index = flat.index(peak) if peak else 0
    result = {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "matrix": matrix,
        "max": peak,
        "peak": {"day": peak_index // 24, "hour": peak_index % 24, "count": peak},
        "timezone": settings.APP_TIMEZONE,
    }
    await cache.set(key, result, ttl=600)
    return result


@router.get("/languages", summary="FIRs by language, with the supported-language catalogue")
async def language_mix(user: Viewer, db: DbDep) -> dict:
    rows = (await db.execute(
        select(FIRReport.language, func.count(FIRReport.id)).group_by(FIRReport.language)
    )).all()
    counts = {lang or "pending": n for lang, n in rows}
    return {
        "counts": [
            {"code": code, "name": LANGUAGES.get(code, {}).get("name", code), "native": LANGUAGES.get(code, {}).get("native"),
             "count": n}
            for code, n in sorted(counts.items(), key=lambda kv: -kv[1])
        ],
        "supported": [{"code": c, **meta} for c, meta in LANGUAGES.items()],
        "embedding_model": settings.EMBEDDING_MODEL,
    }


@router.get("/timeline", summary="Compact incident points for the command-center time-lapse")
async def timeline(user: Viewer, db: DbDep, redis: RedisDep, days: int = Query(90, ge=7, le=365)) -> dict:
    cache = CacheManager(redis, namespace="analytics")
    if cached := await cache.get(f"timeline:{days}"):
        return cached
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (await db.execute(
        select(Crime.latitude, Crime.longitude, Crime.occurred_at, Crime.crime_type, Crime.severity, Crime.series_id)
        .where(Crime.occurred_at >= since).order_by(Crime.occurred_at)
    )).all()
    result = {
        "since": since.isoformat(),
        "until": datetime.now(UTC).isoformat(),
        "points": [
            [round(r.latitude, 5), round(r.longitude, 5), int(r.occurred_at.timestamp()), r.crime_type, r.severity,
             r.series_id]
            for r in rows
        ],
    }
    await cache.set(f"timeline:{days}", result, ttl=300)
    return result


@router.get("/search", summary="Search cases, FIRs and link entities in any language")
async def global_search(user: Analyst, db: DbDep, q: str = Query(..., min_length=2, max_length=200)) -> dict:
    term = q.strip()
    like = f"%{term}%"
    cases = (await db.execute(
        select(Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.occurred_at, Crime.description)
        .where(or_(Crime.case_number.ilike(like), Crime.description.ilike(like), Crime.district.ilike(like)))
        .order_by(Crime.occurred_at.desc()).limit(6)
    )).all()
    firs = (await db.execute(
        select(FIRReport.id, FIRReport.fir_number, FIRReport.language, FIRReport.crime_id)
        .where(or_(FIRReport.fir_number.ilike(like), FIRReport.raw_text.ilike(like))).limit(5)
    )).all()
    semantic = []
    if len(term) >= 8:
        vector = await run_in_threadpool(embed_text, term)
        distance = Crime.embedding.cosine_distance(vector)
        semantic = (await db.execute(
            select(Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.occurred_at, Crime.description,
                   (1 - distance).label("similarity"))
            .where(Crime.embedding.is_not(None)).order_by(distance).limit(6)
        )).all()
    return {
        "query": term,
        "language": analyse(term).language_name,
        "cases": [_case(r) for r in cases],
        "semantic": [{**_case(r), "similarity": round(float(r.similarity), 3)} for r in semantic],
        "firs": [{"id": str(r.id), "fir_number": r.fir_number, "language": r.language,
                  "crime_id": str(r.crime_id) if r.crime_id else None} for r in firs],
        "entities": await entity_graph.search(db, term, limit=6),
    }


def _case(r) -> dict:
    return {
        "id": str(r.id),
        "case_number": r.case_number,
        "crime_type": r.crime_type,
        "district": r.district,
        "occurred_at": r.occurred_at.isoformat(),
        "snippet": (r.description or "")[:140],
    }
