"""Shared Redis client, request dependency and a namespaced JSON cache."""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlsplit

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_pool: Redis | None = None


def redacted_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{parts.path}"


async def get_redis_pool() -> Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_connect_timeout=5,
            health_check_interval=30,
        )
        logger.info("redis_pool_created", url=redacted_url(settings.REDIS_URL))
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield await get_redis_pool()


class CacheManager:
    """JSON cache with key namespacing. Cache failures degrade to a miss, never to an error."""

    def __init__(self, redis: Redis, namespace: str = "crimeai") -> None:
        self.redis = redis
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self.redis.get(self._key(key))
        except aioredis.RedisError as exc:
            logger.warning("cache_get_failed", key=key, error=str(exc))
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            await self.redis.set(
                self._key(key), json.dumps(value, default=str), ex=ttl or settings.REDIS_CACHE_TTL
            )
        except aioredis.RedisError as exc:
            logger.warning("cache_set_failed", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        try:
            await self.redis.delete(self._key(key))
        except aioredis.RedisError as exc:
            logger.warning("cache_delete_failed", key=key, error=str(exc))

    async def invalidate_pattern(self, pattern: str) -> int:
        deleted = 0
        try:
            batch: list[str] = []
            async for key in self.redis.scan_iter(match=self._key(pattern), count=500):
                batch.append(key)
                if len(batch) >= 500:
                    deleted += await self.redis.unlink(*batch)
                    batch.clear()
            if batch:
                deleted += await self.redis.unlink(*batch)
        except aioredis.RedisError as exc:
            logger.warning("cache_invalidate_failed", pattern=pattern, error=str(exc))
        return deleted


async def eviction_policy(redis: Redis) -> str | None:
    """Redis maxmemory-policy, or None where the server forbids CONFIG (common on managed Redis)."""
    try:
        return (await redis.config_get("maxmemory-policy")).get("maxmemory-policy")
    except Exception:
        return None
