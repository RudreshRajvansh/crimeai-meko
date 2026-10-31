"""
Tiger Cloud mirror against a real TimescaleDB: hypertable, sync, continuous aggregates, and a changed crime
replacing its row. Runs when TIGER_TEST_URL points at a TimescaleDB database (a Tiger Cloud service or
`docker run timescale/timescaledb`); skipped otherwise.
"""
import os
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from app.core.config import settings
from app.integrations import tiger
from app.models.crime import Crime

pytestmark = pytest.mark.skipif(not os.environ.get("TIGER_TEST_URL"), reason="TIGER_TEST_URL not set")


async def test_crimes_are_mirrored_and_aggregated_per_deployment(db_session, monkeypatch):
    monkeypatch.setattr(settings, "TIGER_DEPLOYMENT", f"test-{uuid.uuid4().hex[:8]}")
    conn = await asyncpg.connect(os.environ["TIGER_TEST_URL"])
    try:
        await tiger.ensure_schema(conn)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        crimes = [Crime(crime_type="theft", severity=2, city="Delhi", district="Saket", latitude=28.5, longitude=77.2,
                        occurred_at=now - timedelta(days=d, hours=h), case_number=f"DL-TG-{d}-{h}", description="x")
                  for d, h in ((1, 0), (1, 1), (40, 0))]
        db_session.add_all(crimes)
        await db_session.commit()

        assert (await tiger.sync(db_session, conn))["synced"] == 3
        assert (await tiger.sync(db_session, conn))["synced"] == 0, "only changes are copied again"
        crimes[0].occurred_at = now - timedelta(days=2)
        await db_session.commit()
        assert (await tiger.sync(db_session, conn))["synced"] == 1
        await tiger.refresh(conn)

        o = await tiger.overview(conn, months=3, days=30)
        assert o["rows"] == 3, "a changed crime replaces its row instead of adding one"
        assert sum(m["count"] for m in o["monthly"]) == 3
        assert sum(h["count"] for h in o["hours"]) == 2, "the 40-day-old crime is outside the hour-of-day window"
        assert set(o["aggregates"]) >= {"crime_daily", "crime_hourly"}
    finally:
        await conn.execute("DELETE FROM crime_events WHERE deployment = $1", settings.TIGER_DEPLOYMENT)
        await conn.execute("DELETE FROM crimeai_sync WHERE name = $1", f"crimes:{settings.TIGER_DEPLOYMENT}")
        await conn.close()
