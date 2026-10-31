"""Scheduled reports."""
from __future__ import annotations

from celery import shared_task

from app.ml import registry
from app.services.briefing import BRIEFING, build_briefing, render_pdf
from app.services.storage import get_document_store
from app.workers.runtime import run, task_lock, task_resources


@shared_task(name="app.workers.tasks.report_tasks.generate_daily_briefing")
def generate_daily_briefing() -> dict:
    async def _run():
        async with task_resources() as (db, redis), task_lock(redis, "daily_briefing", 900) as acquired:
            if not acquired:
                return {"status": "skipped"}
            brief = await build_briefing(db)
            key = f"reports/briefings/{brief['date']}.pdf"
            url = await get_document_store().put(key, render_pdf(brief), "application/pdf")
            version = await registry.save_json(db, BRIEFING, brief, metadata={"pdf_url": url})
            await db.commit()
            return {"status": "complete", "version": version, "pdf_url": url}
    return run(_run)
