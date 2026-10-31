"""Celery application: queues, routing, reliability settings and the beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)

celery_app = Celery(
    "crimeai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.ml_tasks",
        "app.workers.tasks.nlp_tasks",
        "app.workers.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # At-least-once delivery: a task is acknowledged only after it finishes, and
    # every task is written to be idempotent so redelivery is harmless.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    task_soft_time_limit=1500,
    task_time_limit=1800,
    broker_transport_options={"visibility_timeout": 3600},
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    task_default_queue="default",
    task_queues=(Queue("default"), Queue("ml"), Queue("nlp")),
    task_routes={
        "app.workers.tasks.ml_tasks.*": {"queue": "ml"},
        "app.workers.tasks.nlp_tasks.*": {"queue": "nlp"},
        "app.workers.tasks.report_tasks.*": {"queue": "default"},
    },
    beat_schedule={
        "refresh-forecasts-hourly": {
            "task": "app.workers.tasks.ml_tasks.refresh_forecasts",
            "schedule": crontab(minute=5),
        },
        "retrain-hotspot-nightly": {
            "task": "app.workers.tasks.ml_tasks.retrain_hotspot_model",
            "schedule": crontab(minute=30, hour=2),
        },
        "crime-clustering-6h": {
            "task": "app.workers.tasks.ml_tasks.run_crime_clustering",
            "schedule": crontab(minute=15, hour="*/6"),
        },
        "series-detection-hourly": {
            "task": "app.workers.tasks.ml_tasks.run_series_detection",
            "schedule": crontab(minute=20),
        },
        "embedding-sweep-30min": {
            "task": "app.workers.tasks.ml_tasks.run_batch_embedding",
            "schedule": crontab(minute="*/30"),
        },
        "custody-deadlines-6h": {
            "task": "app.workers.tasks.ml_tasks.run_custody_scan",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "fir-sweep-10min": {
            "task": "app.workers.tasks.nlp_tasks.process_pending_firs",
            "schedule": crontab(minute="*/10"),
        },
        "daily-briefing": {
            "task": "app.workers.tasks.report_tasks.generate_daily_briefing",
            "schedule": crontab(minute=0, hour=1),  # 06:30 IST, ahead of morning roll call
        },
    },
)
