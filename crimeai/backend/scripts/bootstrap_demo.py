#!/usr/bin/env python3
"""
First-run warm-up for a freshly seeded database.

  python scripts/bootstrap_demo.py

Runs, in dependency order, the jobs the scheduler would otherwise spread over a
day: read the seeded FIRs, embed every case, train the hotspot model, build the
forecast, cluster, detect series, link shared identifiers and scan custody
deadlines. Every job is idempotent, so running this twice is harmless.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.workers.tasks import ml_tasks, nlp_tasks

setup_logging(log_level=settings.LOG_LEVEL, log_format="console")


def step(label: str, job, **kwargs) -> dict:
    started = time.monotonic()
    print(f"  {label:<34}", end="", flush=True)
    result = job(**kwargs)
    print(f"done ({time.monotonic() - started:.0f}s)", flush=True)
    return result


def embed_all() -> dict:
    total = 0
    while (batch := ml_tasks.run_batch_embedding(limit=1000).get("embedded", 0)) > 0:
        total += batch
    return {"embedded": total}


if __name__ == "__main__":
    step("Reading seeded FIRs", nlp_tasks.process_pending_firs, batch_size=1000)
    step("Embedding case narratives", embed_all)
    step("Training hotspot model", ml_tasks.retrain_hotspot_model)
    step("Building risk forecast", ml_tasks.refresh_forecasts)
    step("Clustering incidents", ml_tasks.run_crime_clustering)
    step("Detecting crime series", ml_tasks.run_series_detection)
    step("Linking shared identifiers", ml_tasks.run_entity_linking)
    step("Scanning custody deadlines", ml_tasks.run_custody_scan)
