"""
Tiger Data (Tiger Cloud, TimescaleDB): the crime time series.

YugabyteDB stays the system of record. Every crime is mirrored as one row of a hypertable partitioned by time;
continuous aggregates keep hourly and daily counts per district and crime type, bucketed in Indian time, and
chunks older than 90 days are compressed. Rows carry the deployment they came from, so a laptop and a cloud server
can share one Tiger service without counting each other's crimes. The dashboard's trend and hour-of-day charts read the aggregates, so
they stay fast as years of incidents accumulate. Only the fields the charts need are mirrored: no names, text or
identifiers.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.models.crime import Crime

SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb",
    """CREATE TABLE IF NOT EXISTS crime_events (
        time timestamptz NOT NULL,
        deployment text NOT NULL,
        crime_id uuid NOT NULL,
        crime_type text NOT NULL,
        district text NOT NULL,
        severity smallint NOT NULL,
        latitude double precision,
        longitude double precision,
        PRIMARY KEY (deployment, crime_id, time))""",
    "SELECT create_hypertable('crime_events', 'time', chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE)",
    "CREATE TABLE IF NOT EXISTS crimeai_sync (name text PRIMARY KEY, watermark timestamptz NOT NULL, synced_at timestamptz NOT NULL)",
    """CREATE MATERIALIZED VIEW IF NOT EXISTS crime_hourly WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
        SELECT time_bucket(INTERVAL '1 hour', time, 'Asia/Kolkata') AS bucket, deployment, district, crime_type,
               count(*) AS crimes, avg(severity)::real AS avg_severity
        FROM crime_events GROUP BY 1, 2, 3, 4 WITH NO DATA""",
    """CREATE MATERIALIZED VIEW IF NOT EXISTS crime_daily WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
        SELECT time_bucket(INTERVAL '1 day', time, 'Asia/Kolkata') AS bucket, deployment, district, crime_type,
               count(*) AS crimes, avg(severity)::real AS avg_severity
        FROM crime_events GROUP BY 1, 2, 3, 4 WITH NO DATA""",
    """SELECT add_continuous_aggregate_policy('crime_hourly', start_offset => NULL, end_offset => INTERVAL '1 hour',
        schedule_interval => INTERVAL '30 minutes', if_not_exists => TRUE)""",
    """SELECT add_continuous_aggregate_policy('crime_daily', start_offset => NULL, end_offset => INTERVAL '1 hour',
        schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)""",
    """ALTER TABLE crime_events SET (timescaledb.compress, timescaledb.compress_segmentby = 'deployment, district',
        timescaledb.compress_orderby = 'time DESC')""",
    "SELECT add_compression_policy('crime_events', INTERVAL '90 days', if_not_exists => TRUE)",
]

_pool: tuple[asyncio.AbstractEventLoop, asyncpg.Pool] | None = None


@asynccontextmanager
async def connection():
    """A connection from this event loop's pool (API), created on first use."""
    global _pool
    if not settings.tiger_enabled:
        raise ExternalServiceError("Tiger Cloud is not configured: set TIGER_DATABASE_URL")
    loop = asyncio.get_running_loop()
    if _pool is None or _pool[0] is not loop:
        try:
            _pool = (loop, await asyncpg.create_pool(settings.TIGER_DATABASE_URL, min_size=1, max_size=4, timeout=20,
                                                     command_timeout=60))
        except (OSError, asyncpg.PostgresError) as exc:
            raise ExternalServiceError("Tiger Cloud could not be reached", detail=type(exc).__name__) from exc
    async with _pool[1].acquire() as conn:
        yield conn


async def ensure_schema(conn: asyncpg.Connection) -> None:
    for statement in SCHEMA:
        await conn.execute(statement)


async def sync(db: AsyncSession, conn: asyncpg.Connection, *, batch: int = 2000) -> dict[str, Any]:
    """Mirror crimes changed since the last sync (by updated_at); a changed crime replaces its row."""
    name, deployment = f"crimes:{settings.TIGER_DEPLOYMENT}", settings.TIGER_DEPLOYMENT
    watermark = await conn.fetchval("SELECT watermark FROM crimeai_sync WHERE name = $1", name) or datetime(1970, 1, 1, tzinfo=UTC)
    synced = 0
    while True:
        rows = (await db.execute(
            select(Crime.id, Crime.occurred_at, Crime.crime_type, Crime.district, Crime.severity, Crime.latitude,
                   Crime.longitude, Crime.updated_at)
            .where(Crime.updated_at > watermark).order_by(Crime.updated_at).limit(batch)
        )).all()
        if not rows:
            break
        async with conn.transaction():
            await conn.execute("DELETE FROM crime_events WHERE deployment = $1 AND crime_id = ANY($2::uuid[])", deployment,
                               [r.id for r in rows])
            await conn.copy_records_to_table("crime_events", records=[
                (r.occurred_at, deployment, r.id, r.crime_type, r.district or "Unknown", int(r.severity or 1), r.latitude,
                 r.longitude) for r in rows],
                columns=["time", "deployment", "crime_id", "crime_type", "district", "severity", "latitude", "longitude"])
            watermark = rows[-1].updated_at
            await conn.execute(
                "INSERT INTO crimeai_sync (name, watermark, synced_at) VALUES ($1, $2, now()) "
                "ON CONFLICT (name) DO UPDATE SET watermark = EXCLUDED.watermark, synced_at = now()", name, watermark)
        synced += len(rows)
        if len(rows) < batch:
            break
    if not synced:
        await conn.execute("UPDATE crimeai_sync SET synced_at = now() WHERE name = $1", name)
    return {"synced": synced, "watermark": watermark.isoformat()}


async def refresh(conn: asyncpg.Connection) -> None:
    """Materialise both aggregates now (the policies keep them current afterwards)."""
    for view in ("crime_hourly", "crime_daily"):
        await conn.execute(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)")


async def overview(conn: asyncpg.Connection, *, months: int = 12, days: int = 90, district: str | None = None) -> dict[str, Any]:
    """Monthly counts and the hour-of-day profile from the continuous aggregates, plus the hypertable's state."""
    monthly = await conn.fetch("""
        SELECT date_part('year', m AT TIME ZONE 'Asia/Kolkata')::int AS year,
               date_part('month', m AT TIME ZONE 'Asia/Kolkata')::int AS month, sum(crimes)::int AS count
        FROM (SELECT time_bucket(INTERVAL '1 month', bucket, 'Asia/Kolkata') AS m, crimes FROM crime_daily
              WHERE bucket >= date_trunc('month', now() AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata'
                               - make_interval(months => $1 - 1)
                AND deployment = $3 AND ($2::text IS NULL OR district = $2)) t
        GROUP BY m ORDER BY m""", months, district, settings.TIGER_DEPLOYMENT)
    hours = await conn.fetch("""
        SELECT date_part('hour', bucket AT TIME ZONE 'Asia/Kolkata')::int AS hour, sum(crimes)::int AS count
        FROM crime_hourly WHERE bucket >= now() - make_interval(days => $1) AND deployment = $3
          AND ($2::text IS NULL OR district = $2)
        GROUP BY 1 ORDER BY 1""", days, district, settings.TIGER_DEPLOYMENT)
    by_hour = {r["hour"]: r["count"] for r in hours}
    chunks = await conn.fetchrow("""
        SELECT count(*)::int AS total, count(*) FILTER (WHERE is_compressed)::int AS compressed
        FROM timescaledb_information.chunks WHERE hypertable_name = 'crime_events'""")
    state = await conn.fetchrow("SELECT watermark, synced_at FROM crimeai_sync WHERE name = $1", f"crimes:{settings.TIGER_DEPLOYMENT}")
    return {
        "enabled": True,
        "monthly": [dict(r) for r in monthly],
        "hours": [{"hour": h, "count": by_hour.get(h, 0)} for h in range(24)],
        "rows": await conn.fetchval("SELECT count(*) FROM crime_events WHERE deployment = $1", settings.TIGER_DEPLOYMENT),
        "deployment": settings.TIGER_DEPLOYMENT,
        "chunks": chunks["total"], "compressed_chunks": chunks["compressed"],
        "aggregates": [r["view_name"] for r in await conn.fetch(
            "SELECT view_name FROM timescaledb_information.continuous_aggregates ORDER BY view_name")],
        "timescaledb": await conn.fetchval("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"),
        "synced_at": state["synced_at"].isoformat() if state else None,
        "days": days, "months": months, "district": district,
    }
