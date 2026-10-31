"""Helpers for running async service code inside synchronous Celery tasks."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from typing import TypeVar

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import LockError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import worker_session

T = TypeVar("T")


def run(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Each task gets a fresh event loop; nothing loop-bound leaks between tasks."""
    return asyncio.run(coro_factory())


@asynccontextmanager
async def task_resources() -> AsyncGenerator[tuple[AsyncSession, Redis], None]:
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        async with worker_session() as db:
            yield db, redis
    finally:
        await redis.aclose()


@asynccontextmanager
async def task_lock(redis: Redis, name: str, ttl_seconds: int) -> AsyncGenerator[bool, None]:
    """Cluster-wide mutex so overlapping beat runs of the same job never execute twice."""
    lock = redis.lock(f"lock:{name}", timeout=ttl_seconds, blocking=False)
    acquired = await lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            with suppress(LockError):
                await lock.release()
