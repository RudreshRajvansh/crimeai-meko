"""Async SQLAlchemy engine, request-scoped sessions and worker-scoped sessions."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_connect_args = {"statement_cache_size": settings.DB_STATEMENT_CACHE_SIZE}


async def _vector_as_text(conn: Any) -> None:
    with suppress(ValueError):  # the vector extension is not installed in this database yet
        await conn.set_type_codec("vector", schema="public", encoder=str, decoder=str, format="text")


def _register_types(dbapi_connection: Any, _record: Any) -> None:
    # YugabyteDB gives pgvector's `vector` a fixed OID inside the range asyncpg reserves for built-in types, so
    # asyncpg refuses it ("unhandled standard data type") instead of falling back to text as it does on PostgreSQL.
    # pgvector's SQLAlchemy type already sends and reads vectors as text, so a text codec restores that.
    dbapi_connection.run_async(_vector_as_text)


def create_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Async engine for YugabyteDB (also correct on PostgreSQL)."""
    new_engine = create_async_engine(url, **kwargs)
    event.listen(new_engine.sync_engine, "connect", _register_types)
    return new_engine


if settings.APP_ENV == "test":
    engine = create_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=_connect_args)
else:
    engine = create_engine(
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
    task_engine = create_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=_connect_args)
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
