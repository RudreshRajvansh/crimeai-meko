"""Live system view: data volumes, queues, workers, model registry and schedule."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.v1.dependencies.auth import Analyst
from app.core.config import settings
from app.db.redis import get_redis
from app.db.session import get_db
from app.ml import registry
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.crime import Crime
from app.models.entity import Entity, EntityMention
from app.models.fir import FIRReport
from app.models.ml_artifact import MLArtifact
from app.nlp.lexicons import LANGUAGES
from app.realtime.broker import broker

router = APIRouter()
_STARTED = time.time()
_ARTIFACTS = [registry.HOTSPOT_MODEL, registry.HOTSPOT_FORECAST, registry.RISK_SCORES, registry.CLUSTERS,
              registry.CRIME_SERIES, "daily_briefing"]


def _ping_workers() -> list[str]:
    from app.workers.celery_app import celery_app

    try:
        replies = celery_app.control.ping(timeout=0.6) or []
    except Exception:
        return []
    return sorted(name for reply in replies for name in reply)


@router.get("/status")
async def system_status(
    user: Analyst,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    async def count(model, *where):
        return (await db.execute(select(func.count(model.id)).where(*where))).scalar_one()

    queues = {}
    for name in ("default", "ml", "nlp"):
        try:
            queues[name] = await redis.llen(name)
        except Exception:
            queues[name] = None

    latest = (await db.execute(
        select(MLArtifact.name, func.max(MLArtifact.version), func.max(MLArtifact.created_at))
        .where(MLArtifact.name.in_(_ARTIFACTS)).group_by(MLArtifact.name)
    )).all()
    model = await registry.latest(db, registry.HOTSPOT_MODEL)
    from app.workers.celery_app import celery_app

    return {
        "uptime_seconds": int(time.time() - _STARTED),
        "version": settings.APP_VERSION,
        "data": {
            "cases": await count(Crime),
            "embedded_cases": await count(Crime, Crime.embedding.is_not(None)),
            "firs": await count(FIRReport),
            "firs_analysed": await count(FIRReport, FIRReport.nlp_status == "completed"),
            "entities": await count(Entity),
            "entity_links": await count(EntityMention),
            "linking_entities": await count(Entity, Entity.case_count >= 2),
            "open_alerts": await count(Alert, Alert.is_resolved.is_(False)),
            "audit_events": await count(AuditLog),
        },
        "queues": queues,
        "workers": await run_in_threadpool(_ping_workers),
        "websocket_clients": broker.connection_count,
        "artifacts": [
            {"name": name, "version": version, "updated_at": created.isoformat()} for name, version, created in latest
        ],
        "hotspot_model": None if model is None else {
            "version": model.version,
            "roc_auc": model.metadata.get("roc_auc"),
            "baseline_roc_auc": model.metadata.get("baseline_roc_auc"),
            "beats_baseline": model.metadata.get("beats_baseline"),
        },
        "nlp": {
            "embedding_model": settings.EMBEDDING_MODEL,
            "languages_supported": len(LANGUAGES),
            "zero_shot_enabled": settings.ENABLE_ZERO_SHOT,
        },
        "schedule": [
            {"name": name, "task": spec["task"].rsplit(".", 1)[-1], "schedule": str(spec["schedule"])}
            for name, spec in celery_app.conf.beat_schedule.items()
        ],
    }
