"""Async SQLAlchemy engine, request-scoped sessions and worker-scoped sessions."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_connect_args = {"statement_cache_size": settings.DB_STATEMENT_CACHE_SIZE}

if settings.APP_ENV == "test":
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=_connect_args)
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.APP_DEBUG and settings.is_development,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=1800,
        connect_args=_connect_args,
    )

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped unit of work: commit on success, roll back on any error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def worker_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Session for Celery tasks. Each task runs its own event loop, so it gets a
    private NullPool engine instead of sharing the API's pooled connections.
    """
    task_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=_connect_args)
    session_factory = async_sessionmaker(task_engine, expire_on_commit=False, autoflush=False)
    try:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await task_engine.dispose()


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("db_health_check_failed", error=str(exc))
        return False
