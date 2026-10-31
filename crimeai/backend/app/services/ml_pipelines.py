"""
Write side of the ML system, run by Celery workers.

Each pipeline reads from Postgres, does CPU-heavy work, and writes a new
versioned artifact. Outputs are published by invalidating the API's short
registry cache, so the next read picks the new version up.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import ALERTS_RAISED
from app.db.redis import CacheManager
from app.ml import registry
from app.ml.clustering.dbscan import find_optimal_eps, run_dbscan
from app.ml.linkage.series_detector import Incident, detect_series
from app.ml.prediction import hotspot_predictor
from app.ml.prediction.risk_scorer import compute_district_risk_scores, score_single_crime
from app.ml.similarity.crime_similarity import crime_document, crimes_missing_embeddings, store_embeddings
from app.ml.similarity.embeddings import embed_batch
from app.models.crime import Crime
from app.nlp.multilingual import detect_language
from app.realtime.broker import publish_alert
from app.repositories.alert_repository import AlertRepository
from app.repositories.crime_repository import CrimeRepository
from app.services.custody_clock import compute_deadline

logger = get_logger(__name__)

OPEN_STATUSES = ("reported", "under_investigation")


async def _publish(redis: Redis, name: str) -> None:
    await CacheManager(redis, namespace="ml").delete(f"registry:{name}")


async def _records(db: AsyncSession, since: datetime) -> list[dict[str, Any]]:
    rows = await CrimeRepository(db).get_records(since=since)
    return [
        {
            "id": str(r.id),
            "district": r.district,
            "crime_type": r.crime_type,
            "severity": r.severity,
            "occurred_at": r.occurred_at,
            "lat": float(r.latitude),
            "lng": float(r.longitude),
        }
        for r in rows
    ]


async def run_clustering(
    db: AsyncSession, redis: Redis, eps_km: float | None = None, min_samples: int | None = None,
    from_date: datetime | None = None, auto_eps: bool = False,
) -> dict[str, Any]:
    from_date = from_date or datetime.now(UTC) - timedelta(days=365)
    repo = CrimeRepository(db)
    records = await repo.get_all_coordinates(from_date=from_date)
    if len(records) < 3:
        return {"status": "insufficient_data", "n_records": len(records)}
    if auto_eps:
        eps_km = find_optimal_eps(records, min_samples=min_samples or settings.DBSCAN_MIN_SAMPLES)
    result = run_dbscan(crime_records=records, eps_km=eps_km, min_samples=min_samples)
    await repo.bulk_update_clusters(result.assignments)
    summary = {
        "num_clusters": result.num_clusters,
        "noise_points": result.noise_points,
        "total_points": result.total_points,
        "coverage_pct": result.coverage_pct,
        "parameters": result.parameters,
        "clusters": result.cluster_summaries,
    }
    version = await registry.save_json(db, registry.CLUSTERS, summary, metadata=result.parameters)
    await db.commit()
    await _publish(redis, registry.CLUSTERS)
    return {"status": "complete", "version": version, **{k: v for k, v in summary.items() if k != "clusters"}}


async def train_hotspot_model(db: AsyncSession, redis: Redis) -> dict[str, Any]:
    records = await _records(db, since=datetime.now(UTC) - timedelta(days=365))
    model, report = hotspot_predictor.train_hotspot_model(records, min_rows=settings.HOTSPOT_MIN_TRAINING_ROWS)
    version = await registry.save_object(db, registry.HOTSPOT_MODEL, model, metadata=report.to_dict())
    await db.commit()
    if not report.beats_baseline:
        logger.warning("hotspot_model_below_baseline", version=version, roc_auc=report.roc_auc,
                       baseline=report.baseline_roc_auc)
    return {"status": "trained", "version": version, "report": report.to_dict()}


async def forecast_hotspots(db: AsyncSession, redis: Redis) -> dict[str, Any]:
    artifact = await registry.latest(db, registry.HOTSPOT_MODEL)
    if artifact is None:
        trained = await train_hotspot_model(db, redis)
        artifact = await registry.latest(db, registry.HOTSPOT_MODEL)
        if artifact is None:
            return trained
    records = await _records(db, since=datetime.now(UTC) - timedelta(days=60))
    timeline = hotspot_predictor.forecast(artifact.as_object(), records)
    version = await registry.save_json(
        db, registry.HOTSPOT_FORECAST, timeline,
        metadata={"model_version": artifact.version, "beats_baseline": artifact.metadata.get("beats_baseline")},
    )
    await db.commit()
    await _publish(redis, registry.HOTSPOT_FORECAST)
    return {"status": "complete", "version": version, "model_version": artifact.version, "blocks": len(timeline)}


async def compute_risk_map(db: AsyncSession, redis: Redis) -> dict[str, Any]:
    lookback = settings.RISK_LOOKBACK_DAYS
    records = await _records(db, since=datetime.now(UTC) - timedelta(days=lookback))
    scores = compute_district_risk_scores(records, lookback_days=lookback, scale=settings.RISK_SCORE_SCALE)
    version = await registry.save_json(
        db, registry.RISK_SCORES, scores, metadata={"lookback_days": lookback, "scale": settings.RISK_SCORE_SCALE}
    )
    await db.commit()
    await _publish(redis, registry.RISK_SCORES)
    raised = await _raise_risk_transition_alerts(db, redis, scores)
    return {"status": "complete", "version": version, "districts": len(scores), "alerts_raised": raised}


async def _raise_risk_transition_alerts(db: AsyncSession, redis: Redis, scores: dict[str, dict]) -> int:
    """Alert only when a district moves up into high/critical; a steady state is not news."""
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    previous = await redis.hgetall("risk:last_level")
    alerts = AlertRepository(db)
    raised = []
    for district, data in scores.items():
        level = data["level"]
        before = previous.get(district, "low")
        if rank[level] >= rank["high"] and rank[level] > rank.get(before, 0):
            alert = await alerts.create(
                title=f"{level.capitalize()} risk: {district}",
                message=(
                    f"Risk index rose from {before} to {level} ({data['score']:.0f}/100, trend {data['trend']}). "
                    f"{data['components']['recent_7d']} incidents in the last 7 days. Review shift deployment."
                ),
                alert_type="high_risk",
                severity=level,
                district=district,
                target_role="police",
                dedupe_key=f"risk:{district}:{level}",
            )
            raised.append(alert)
    if scores:
        await redis.hset("risk:last_level", mapping={d: s["level"] for d, s in scores.items()})
    await db.commit()
    for alert in raised:
        ALERTS_RAISED.labels("high_risk").inc()
        await publish_alert(redis, alert)
    return len(raised)


async def score_crime(db: AsyncSession, crime_id: uuid.UUID) -> dict[str, Any]:
    crime = await db.get(Crime, crime_id)
    if crime is None:
        return {"status": "not_found"}
    risk = await registry.latest(db, registry.RISK_SCORES)
    district_score = (risk.as_json().get(crime.district or "", {}).get("score", 0.0)) if risk else 0.0
    score = score_single_crime(crime.crime_type, crime.severity, district_score, crime.occurred_at)
    await CrimeRepository(db).update_risk_score(crime.id, score)
    await db.commit()
    return {"status": "complete", "risk_score": score}


async def score_all_crimes(db: AsyncSession, redis: Redis | None = None) -> dict[str, Any]:
    """
    Re-score every case against the current district index. Cases created through the API are scored one
    by one; imported and seeded cases are not, and every case's score drifts as its district index moves.
    """
    risk = await registry.latest(db, registry.RISK_SCORES)
    districts = risk.as_json() if risk else {}
    rows = (await db.execute(select(Crime.id, Crime.crime_type, Crime.severity, Crime.district, Crime.occurred_at))).all()
    scores = [
        {"id": r.id, "risk_score": score_single_crime(
            r.crime_type, r.severity, districts.get(r.district or "", {}).get("score", 0.0), r.occurred_at)}
        for r in rows
    ]
    if scores:
        await db.execute(update(Crime), scores)
    await db.commit()
    return {"status": "complete", "scored": len(scores)}


async def embed_crimes(db: AsyncSession, crime_ids: list[uuid.UUID] | None = None, limit: int = 500) -> dict[str, int]:
    if crime_ids:
        rows = (await db.execute(
            select(Crime.id, Crime.crime_type, Crime.sub_type, Crime.description, Crime.district)
            .where(Crime.id.in_(crime_ids))
        )).all()
    else:
        rows = await crimes_missing_embeddings(db, limit=limit)
    if not rows:
        return {"embedded": 0}
    vectors = embed_batch([crime_document(r.crime_type, r.sub_type, r.description, r.district) for r in rows])
    stored = await store_embeddings(db, {r.id: v for r, v in zip(rows, vectors, strict=False)})
    await db.commit()
    return {"embedded": stored}


async def detect_crime_series(db: AsyncSession, redis: Redis, lookback_days: int = 120) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=lookback_days)
    rows = (await db.execute(
        select(Crime.id, Crime.crime_type, Crime.latitude, Crime.longitude, Crime.occurred_at,
               Crime.description, Crime.district, Crime.embedding, Crime.series_id)
        .where(Crime.occurred_at >= since)
    )).all()
    incidents = [
        Incident(
            id=str(r.id), crime_type=r.crime_type, lat=float(r.latitude), lng=float(r.longitude),
            occurred_at=r.occurred_at, text=r.description or "", district=r.district,
            embedding=np.asarray(r.embedding) if r.embedding is not None else None,
            language=detect_language(r.description or "")[0],
        )
        for r in rows
    ]
    series = detect_series(
        incidents,
        radius_km=settings.SERIES_RADIUS_KM,
        window_days=settings.SERIES_WINDOW_DAYS,
        min_similarity=settings.SERIES_MIN_SIMILARITY,
        min_size=settings.SERIES_MIN_SIZE,
    )
    known = {r.series_id for r in rows if r.series_id}
    await CrimeRepository(db).assign_series({cid: s.series_id for s in series for cid in s.incident_ids})
    payload = [s.to_dict() for s in series]
    version = await registry.save_json(db, registry.CRIME_SERIES, payload, metadata={"lookback_days": lookback_days})

    alerts = AlertRepository(db)
    new_alerts = []
    for s in series:
        if s.series_id in known:
            continue
        where = ", ".join(s.districts) or "multiple areas"
        new_alerts.append(await alerts.create(
            title=f"Possible crime series: {len(s.incident_ids)} linked {s.crime_type.replace('_', ' ')} incidents",
            message=(
                f"{len(s.incident_ids)} incidents within {s.radius_km:.1f} km in {where} between "
                f"{s.first_seen:%d %b} and {s.last_seen:%d %b} share a similar modus operandi "
                f"(cohesion {s.cohesion:.2f}). Review series {s.series_id} for linked investigation."
            ),
            alert_type="crime_series",
            severity="high" if len(s.districts) > 1 or len(s.incident_ids) >= 5 else "medium",
            latitude=s.centroid[0],
            longitude=s.centroid[1],
            district=s.districts[0] if s.districts else None,
            target_role="analyst",
            dedupe_key=s.series_id,
        ))
    await db.commit()
    await _publish(redis, registry.CRIME_SERIES)
    for alert in new_alerts:
        ALERTS_RAISED.labels("crime_series").inc()
        await publish_alert(redis, alert)
    return {"status": "complete", "version": version, "series": len(series), "new": len(new_alerts)}


async def scan_custody_deadlines(db: AsyncSession, redis: Redis) -> dict[str, Any]:
    cases = await CrimeRepository(db).custody_cases(OPEN_STATUSES)
    alerts = AlertRepository(db)
    since = datetime.now(UTC) - timedelta(days=120)
    raised = []
    for crime in cases:
        deadline = compute_deadline(crime)
        if deadline.escalation is None:
            continue
        key = f"custody:{crime.id}:{deadline.escalation}"
        if await alerts.exists_open("custody_deadline", key, since):
            continue
        when = "is overdue" if deadline.days_remaining < 0 else f"is due in {deadline.days_remaining} day(s)"
        raised.append(await alerts.create(
            title=f"Chargesheet deadline {deadline.status.replace('_', ' ')}: {crime.case_number or crime.id}",
            message=(
                f"Accused in custody since {deadline.arrested_at:%d %b %Y}. The {deadline.limit_days}-day limit "
                f"under BNSS s.187(3) {when} ({deadline.deadline:%d %b %Y}). File the final report or the accused "
                f"becomes entitled to default bail."
            ),
            alert_type="custody_deadline",
            severity=deadline.escalation,
            district=crime.district,
            related_crime_id=crime.id,
            assigned_to=crime.assigned_officer_id,
            target_role="police",
            dedupe_key=key,
        ))
    await db.commit()
    for alert in raised:
        ALERTS_RAISED.labels("custody_deadline").inc()
        await publish_alert(redis, alert)
    return {"status": "complete", "open_custody_cases": len(cases), "alerts_raised": len(raised)}


async def link_all_cases(db: AsyncSession, redis: Redis) -> dict[str, Any]:
    """Backfill the link graph from every case narrative and every analysed FIR."""
    from app.models.fir import FIRReport
    from app.services import entity_graph

    linked_ids: list[uuid.UUID] = []
    crimes = (await db.execute(select(Crime.id, Crime.description, Crime.occurred_at))).all()
    for crime_id, description, occurred_at in crimes:
        if description:
            linked_ids += await entity_graph.link_crime(db, crime_id, description, occurred_at=occurred_at)
    firs = (await db.execute(
        select(FIRReport.id, FIRReport.crime_id, FIRReport.raw_text, FIRReport.incident_date)
        .where(FIRReport.crime_id.is_not(None))
    )).all()
    for fir_id, crime_id, text, incident_date in firs:
        linked_ids += await entity_graph.link_crime(db, crime_id, text, fir_id, incident_date)
    alerts = await entity_graph.link_alerts(db, linked_ids)
    await db.commit()
    for alert in alerts:
        ALERTS_RAISED.labels("pattern").inc()
        await publish_alert(redis, alert)
    return {"status": "complete", "cases_scanned": len(crimes), "firs_scanned": len(firs),
            "mentions": len(linked_ids), "link_alerts": len(alerts)}
