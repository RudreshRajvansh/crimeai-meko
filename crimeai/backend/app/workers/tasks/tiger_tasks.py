"""Tiger Cloud job: keep the crime hypertable in step with YugabyteDB."""
from __future__ import annotations

import asyncpg
from celery import shared_task

from app.core.config import settings
from app.integrations import tiger
from app.workers.runtime import run, task_lock, task_resources


@shared_task(name="app.workers.tasks.tiger_tasks.sync", autoretry_for=(ConnectionError, OSError), retry_backoff=60,
             max_retries=2)
def sync() -> dict:
    if not settings.tiger_enabled:
        return {"status": "off"}

    async def _run():
        async with task_resources() as (db, redis), task_lock(redis, "tiger_sync", 240) as acquired:
            if not acquired:
                return {"status": "skipped"}
            # A connection of its own: each task run has its own event loop, so the API's pool does not apply.
            conn = await asyncpg.connect(settings.TIGER_DATABASE_URL, timeout=20)
            try:
                return {"status": "complete", **await tiger.sync(db, conn)}
            finally:
                await conn.close()
    return run(_run)
