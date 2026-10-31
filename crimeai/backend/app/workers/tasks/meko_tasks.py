"""Meko jobs: share a registered case with the grid, and keep promoted exclusions cached for link alerts."""
from __future__ import annotations

import uuid

from celery import shared_task

from app.core.config import settings
from app.core.logging import get_logger
from app.meko import service
from app.workers.runtime import run, task_lock, task_resources

logger = get_logger(__name__)


@shared_task(name="app.workers.tasks.meko_tasks.share_case", autoretry_for=(ConnectionError, OSError),
             retry_backoff=30, max_retries=3)
def share_case(crime_id: str) -> dict:
    if not settings.meko_enabled:
        return {"status": "off"}

    async def _run():
        async with task_resources() as (db, _redis):
            result = await service.share_case(db, uuid.UUID(crime_id))
            if result["status"] != "ok":
                logger.warning("meko_share_failed", crime_id=crime_id, error=result.get("error"))
            return {k: v for k, v in result.items() if k in ("status", "error", "case_ref")}
    return run(_run)


@shared_task(name="app.workers.tasks.meko_tasks.sync_exclusions")
def sync_exclusions() -> dict:
    if not settings.meko_enabled:
        return {"status": "off"}

    async def _run():
        async with task_resources() as (db, redis), task_lock(redis, "meko_exclusions", 300) as acquired:
            if not acquired:
                return {"status": "skipped"}
            return {"status": "complete", "exclusions": await service.sync_exclusions(db)}
    return run(_run)
