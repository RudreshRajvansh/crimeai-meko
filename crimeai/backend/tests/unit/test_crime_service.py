"""Unit tests for CrimeService business logic (mocked repo + cache)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.crime import CrimeCreateRequest


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.keys = AsyncMock(return_value=[])
    return redis


@pytest.mark.asyncio
async def test_generate_case_number_format(mock_db, mock_redis):
    from app.services.crime_service import CrimeService
    svc = CrimeService(db=mock_db, redis=mock_redis)
    cn = svc._generate_case_number()
    year = datetime.now(UTC).year
    assert cn.startswith(f"CRM-{year}-")
    assert len(cn) > 10


@pytest.mark.asyncio
async def test_create_crime_appends_weapon_to_description(mock_db, mock_redis):
    from app.services.crime_service import CrimeService
    svc = CrimeService(db=mock_db, redis=mock_redis)

    fake_crime = MagicMock()
    fake_crime.id = uuid.uuid4()
    fake_crime.crime_type = "assault"
    fake_crime.sub_type = None
    fake_crime.description = "Victim was attacked. Weapon used: knife."
    fake_crime.severity = 3
    fake_crime.latitude = 28.6
    fake_crime.longitude = 77.2
    fake_crime.location_name = None
    fake_crime.address = None
    fake_crime.district = "Central"
    fake_crime.city = "Delhi"
    fake_crime.occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    fake_crime.reported_at = datetime(2024, 1, 1, tzinfo=UTC)
    fake_crime.status = "reported"
    fake_crime.case_number = "CRM-2024-ABC"
    fake_crime.assigned_officer_id = None
    fake_crime.cluster_id = None
    fake_crime.series_id = None
    fake_crime.legal_sections = None
    fake_crime.accused_arrested_at = None
    fake_crime.chargesheet_filed_at = None
    fake_crime.risk_score = None
    fake_crime.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    fake_crime.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

    with (
        patch.object(svc.repo, "get_by_case_number", new_callable=AsyncMock, return_value=None),
        patch.object(svc.repo, "create", new_callable=AsyncMock, return_value=fake_crime),
        patch.object(svc, "_after_write", new_callable=AsyncMock),
        patch("app.services.crime_service.enqueue") as enqueue,
    ):
        req = CrimeCreateRequest(
            crime_type="assault",
            severity=3,
            latitude=28.6,
            longitude=77.2,
            city="Delhi",
            occurred_at=datetime(2024, 1, 1, tzinfo=UTC),
            description="Victim was attacked.",
            weapon_used="knife",
        )
        result = await svc.create_crime(req, created_by=uuid.uuid4())
        assert result.crime_type == "assault"

        # Verify create was called with weapon appended to description
        call_kwargs = svc.repo.create.call_args.kwargs
        assert "knife" in call_kwargs["description"]
        # Side effects run only after the commit, so workers never see an uncommitted row.
        mock_db.commit.assert_awaited()
        assert {c.args[0] for c in enqueue.call_args_list} == {
            "app.workers.tasks.ml_tasks.score_crime_risk",
            "app.workers.tasks.ml_tasks.embed_crime",
        }
