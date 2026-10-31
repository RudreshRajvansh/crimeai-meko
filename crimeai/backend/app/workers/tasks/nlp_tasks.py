"""FIR processing jobs. Safe to deliver more than once: the claim in FIRRepository makes them idempotent."""
from __future__ import annotations

import uuid

from celery import shared_task

from app.core.logging import get_logger
from app.repositories.fir_repository import FIRRepository
from app.services.nlp_service import NLPService
from app.workers.runtime import run, task_lock, task_resources

logger = get_logger(__name__)


@shared_task(
    name="app.workers.tasks.nlp_tasks.process_fir",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=30,
    max_retries=3,
)
def process_fir(fir_id: str) -> dict:
    async def _run():
        async with task_resources() as (db, redis):
            return await NLPService(db, redis).process(uuid.UUID(fir_id))
    return run(_run)


@shared_task(name="app.workers.tasks.nlp_tasks.process_pending_firs")
def process_pending_firs(batch_size: int = 100) -> dict:
    """Sweep for FIRs whose enqueue was lost, whose worker crashed, or whose processing failed transiently."""
    async def _run():
        async with task_resources() as (db, redis), task_lock(redis, "fir_sweep", 900) as acquired:
            if not acquired:
                return {"status": "skipped"}
            service = NLPService(db, redis)
            outcomes: dict[str, int] = {}
            for fir_id in await FIRRepository(db).claimable_ids(limit=batch_size):
                try:
                    status = (await service.process(fir_id))["status"]
                except Exception as exc:
                    logger.warning("fir_sweep_item_failed", fir_id=str(fir_id), error=str(exc))
                    status = "failed"
                outcomes[status] = outcomes.get(status, 0) + 1
            return {"status": "complete", **outcomes}
    return run(_run)
