"""ML and intelligence jobs. Each is idempotent and guarded by a cluster-wide lock."""
from __future__ import annotations

import uuid
from datetime import datetime

from celery import shared_task

from app.core.exceptions import MLServiceError
from app.core.logging import get_logger
from app.services import ml_pipelines
from app.workers.runtime import run, task_lock, task_resources

logger = get_logger(__name__)

_RETRYABLE = {"autoretry_for": (ConnectionError, OSError), "retry_backoff": 30, "retry_backoff_max": 600, "max_retries": 3}


def _locked(name: str, ttl: int, job):
    async def _run():
        async with task_resources() as (db, redis), task_lock(redis, name, ttl) as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "already_running"}
            return await job(db, redis)
    return run(_run)


@shared_task(name="app.workers.tasks.ml_tasks.refresh_forecasts", **_RETRYABLE)
def refresh_forecasts(retrain: bool = False) -> dict:
    """Hourly: recompute the risk index, every case's score and the next-24h shift forecast. Retrains only when asked or nightly."""
    async def job(db, redis):
        outcome = {"risk": await ml_pipelines.compute_risk_map(db, redis)}
        outcome["case_scores"] = await ml_pipelines.score_all_crimes(db, redis)
        try:
            if retrain:
                outcome["training"] = await ml_pipelines.train_hotspot_model(db, redis)
            outcome["forecast"] = await ml_pipelines.forecast_hotspots(db, redis)
        except MLServiceError as exc:
            outcome["forecast"] = {"status": "skipped", "reason": exc.message, "detail": exc.detail}
        return outcome
    return _locked("refresh_forecasts", 1800, job)


@shared_task(name="app.workers.tasks.ml_tasks.retrain_hotspot_model", **_RETRYABLE)
def retrain_hotspot_model() -> dict:
    async def job(db, redis):
        try:
            return await ml_pipelines.train_hotspot_model(db, redis)
        except MLServiceError as exc:
            return {"status": "skipped", "reason": exc.message, "detail": exc.detail}
    return _locked("retrain_hotspot_model", 3600, job)


@shared_task(name="app.workers.tasks.ml_tasks.run_crime_clustering", **_RETRYABLE)
def run_crime_clustering(
    eps_km: float | None = None, min_samples: int | None = None, auto_eps: bool = False, from_date_iso: str | None = None
) -> dict:
    from_date = datetime.fromisoformat(from_date_iso) if from_date_iso else None

    async def job(db, redis):
        return await ml_pipelines.run_clustering(db, redis, eps_km, min_samples, from_date, auto_eps)
    return _locked("crime_clustering", 1800, job)


@shared_task(name="app.workers.tasks.ml_tasks.run_series_detection", **_RETRYABLE)
def run_series_detection() -> dict:
    return _locked("series_detection", 1800, ml_pipelines.detect_crime_series)


@shared_task(name="app.workers.tasks.ml_tasks.run_custody_scan", **_RETRYABLE)
def run_custody_scan() -> dict:
    return _locked("custody_scan", 900, ml_pipelines.scan_custody_deadlines)


@shared_task(name="app.workers.tasks.ml_tasks.score_crime_risk", **_RETRYABLE)
def score_crime_risk(crime_id: str) -> dict:
    async def _run():
        async with task_resources() as (db, _):
            return await ml_pipelines.score_crime(db, uuid.UUID(crime_id))
    return run(_run)


@shared_task(name="app.workers.tasks.ml_tasks.embed_crime", **_RETRYABLE)
def embed_crime(crime_id: str) -> dict:
    async def _run():
        async with task_resources() as (db, _):
            return await ml_pipelines.embed_crimes(db, crime_ids=[uuid.UUID(crime_id)])
    return run(_run)


@shared_task(name="app.workers.tasks.ml_tasks.run_batch_embedding", **_RETRYABLE)
def run_batch_embedding(limit: int = 500) -> dict:
    async def job(db, redis):
        return await ml_pipelines.embed_crimes(db, limit=limit)
    return _locked("batch_embedding", 3600, job)


@shared_task(name="app.workers.tasks.ml_tasks.run_entity_linking", **_RETRYABLE)
def run_entity_linking() -> dict:
    return _locked("entity_linking", 1800, ml_pipelines.link_all_cases)
