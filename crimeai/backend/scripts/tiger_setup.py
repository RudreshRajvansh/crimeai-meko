#!/usr/bin/env python3
"""
Set up the Tiger Cloud (TimescaleDB) mirror of the crime time series.

  python scripts/tiger_setup.py

Creates the crime_events hypertable, the hourly and daily continuous aggregates (Indian time), their refresh
policies and a compression policy; copies every crime from YugabyteDB; materialises the aggregates. Idempotent:
later runs copy only crimes changed since the last sync. The Celery beat job keeps it current afterwards.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.session import create_engine
from app.integrations import tiger


async def main() -> int:
    if not settings.tiger_enabled:
        print("  [!!] TIGER_DATABASE_URL is empty. Create a service at https://console.cloud.timescale.com and put its "
              "connection string in backend/.env.")
        return 1
    conn = await asyncpg.connect(settings.TIGER_DATABASE_URL, timeout=30)
    engine = create_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        await tiger.ensure_schema(conn)
        print("  [ok] hypertable crime_events, continuous aggregates crime_hourly and crime_daily, policies")
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            print(f"  [ok] {(await tiger.sync(db, conn))['synced']} crime(s) copied from YugabyteDB")
        await tiger.refresh(conn)
        o = await tiger.overview(conn)
        print(f"  [ok] aggregates materialised: {o['rows']} rows in {o['chunks']} chunk(s); "
              f"TimescaleDB {o['timescaledb']}; last 12 months: {sum(m['count'] for m in o['monthly'])} crimes")
    finally:
        await conn.close()
        await engine.dispose()
    print("Done. The dashboard's 'Time series · Tiger Cloud' card reads the aggregates.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
