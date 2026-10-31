"""
Fire-and-forget task dispatch for request handlers.

Callers commit first and enqueue second, so a worker never sees a row that is
not yet visible. If the broker is down the request still succeeds; the periodic
sweeps (pending FIRs, missing embeddings, unscored crimes) pick the work up later.
"""
from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def enqueue(task_name: str, *args: Any, **kwargs: Any) -> str | None:
    from app.workers.celery_app import celery_app

    try:
        return celery_app.send_task(task_name, args=args, kwargs=kwargs).id
    except Exception as exc:
        logger.error("task_enqueue_failed", task=task_name, error=str(exc))
        return None
