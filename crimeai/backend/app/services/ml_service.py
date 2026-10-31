"""
Read side of the ML system, used by the API.

The API never trains models and never reads model files from local disk. It
serves the latest versioned outputs from the registry (Postgres) through a short
Redis cache, and runs only light, bounded inference (query embedding, area
profiles) in a worker thread so the event loop stays free.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis import CacheManager
from app.ml import registry
from app.ml.prediction.suspect_profiler import build_area_profile
from app.ml.similarity.crime_similarity import find_similar_crimes
from app.ml.similarity.embeddings import embed_text
from app.nlp.privacy.redaction import redact
from app.repositories.crime_repository import CrimeRepository

logger = get_logger(__name__)

_REGISTRY_CACHE_TTL = 60


class MLService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.repo = CrimeRepository(db)
        self.cache = CacheManager(redis, namespace="ml")

    async def _latest_output(self, name: str) -> dict[str, Any] | None:
        cached = await self.cache.get(f"registry:{name}")
        if cached is not None:
            return cached
        artifact = await registry.latest(self.db, name)
        if artifact is None:
            return None
        payload = {
            "version": artifact.version,
            "generated_at": artifact.created_at,
            "metadata": artifact.metadata,
            "data": artifact.as_json(),
        }
        await self.cache.set(f"registry:{name}", payload, ttl=_REGISTRY_CACHE_TTL)
        return payload

    @staticmethod
    def _not_ready(what: str, trigger: str) -> dict[str, Any]:
        return {"status": "not_ready", "message": f"No {what} yet. {trigger}", "data": None}

    async def get_clusters(self) -> dict[str, Any]:
        output = await self._latest_output(registry.CLUSTERS)
        return {"status": "ok", **output} if output else self._not_ready("clustering results", "POST /ml/cluster")

    async def get_hotspot_forecast(self) -> dict[str, Any]:
        output = await self._latest_output(registry.HOTSPOT_FORECAST)
        if not output:
            return self._not_ready("hotspot forecast", "POST /ml/hotspot-prediction")
        return {"status": "ok", **output}

    async def get_risk_map(self) -> dict[str, Any]:
        output = await self._latest_output(registry.RISK_SCORES)
        return {"status": "ok", **output} if output else self._not_ready("risk map", "POST /ml/hotspot-prediction")

    async def get_series(self, active_within_days: int | None = None) -> dict[str, Any]:
        output = await self._latest_output(registry.CRIME_SERIES)
        if not output:
            return self._not_ready("crime series", "POST /intel/series/detect")
        series = output["data"]
        if active_within_days:
            cutoff = (datetime.now(UTC) - timedelta(days=active_within_days)).isoformat()
            series = [s for s in series if s["last_seen"] >= cutoff]
        return {"status": "ok", **output, "data": series}

    async def find_similar(
        self, query_text: str, top_k: int = 5, crime_type_filter: str | None = None, min_similarity: float = 0.5
    ) -> list[dict[str, Any]]:
        vector = await run_in_threadpool(embed_text, redact(query_text).text)
        return await find_similar_crimes(
            self.db, vector, top_k=top_k, crime_type_filter=crime_type_filter, min_similarity=min_similarity
        )

    async def get_area_profile(self, district: str, lookback_days: int = 60) -> dict[str, Any]:
        key = f"profile:{district}:{lookback_days}"
        cached = await self.cache.get(key)
        if cached:
            return {**cached, "from_cache": True}
        since = datetime.now(UTC) - timedelta(days=lookback_days)
        rows = await self.repo.get_records(since=since, district=district)
        records = [
            {
                "id": str(r.id),
                "district": r.district or district,
                "crime_type": r.crime_type,
                "sub_type": None,
                "severity": r.severity,
                "occurred_at": r.occurred_at.isoformat(),
                "latitude": float(r.latitude),
                "longitude": float(r.longitude),
            }
            for r in rows
        ]
        profile = await run_in_threadpool(build_area_profile, records, district=district, lookback_days=lookback_days)
        await self.cache.set(key, profile, ttl=1800)
        return profile

    async def model_card(self) -> dict[str, Any]:
        """What is deployed, how it was evaluated, and its known limits."""
        model = await registry.latest(self.db, registry.HOTSPOT_MODEL)
        return {
            "hotspot_model": {
                "version": model.version if model else None,
                "trained_at": model.created_at if model else None,
                "evaluation": model.metadata if model else None,
                "history": await registry.history(self.db, registry.HOTSPOT_MODEL),
                "intended_use": "Shift-level patrol prioritisation across districts. Not for decisions about individuals.",
                "limitations": [
                    "Trained on reported crime, which reflects reporting and patrol intensity as well as offending.",
                    "Areas that receive more patrols generate more reports; outputs must be reviewed for feedback loops.",
                    "Probabilities describe district-shift blocks, never people.",
                ],
            },
            "embedding_model": f"{settings.EMBEDDING_MODEL} ({settings.EMBEDDING_DIM}-d, PII redacted before encoding)",
            "risk_index": "Absolute 0-100 harm-weighted index with recency weighting and own-baseline trend",
        }
