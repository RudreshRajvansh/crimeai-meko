"""
Investigative intelligence: linked crime series and custody deadlines.

Both turn passive records into work items: "these five incidents across two
police stations are probably one offender", and "this accused walks free on
default bail in 4 days unless the chargesheet is filed".
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Admin, Analyst, Officer
from app.api.v1.endpoints.ml import queue_job
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.rate_limit import limiter
from app.db.redis import get_redis
from app.db.session import get_db
from app.repositories.crime_repository import CrimeRepository
from app.schemas.crime import CrimeResponse
from app.services import swarm
from app.services.custody_clock import compute_deadline
from app.services.ml_pipelines import OPEN_STATUSES
from app.services.ml_service import MLService

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


@router.get("/series", summary="Candidate crime series (linked incidents)")
async def list_series(
    user: Analyst, db: DbDep, redis: RedisDep, active_within_days: int | None = Query(30, ge=1, le=365)
) -> dict:
    return await MLService(db, redis).get_series(active_within_days=active_within_days)


@router.get("/series/{series_id}/incidents", response_model=list[CrimeResponse])
async def series_incidents(series_id: str, user: Analyst, db: DbDep) -> list[CrimeResponse]:
    crimes, _ = await CrimeRepository(db).list_crimes(series_id=series_id, limit=200)
    return [CrimeResponse.model_validate(c) for c in crimes]


@router.post("/series/detect", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_ML)
async def detect_series(request: Request, user: Analyst, redis: RedisDep) -> dict:
    return await queue_job(redis, user, "app.workers.tasks.ml_tasks.run_series_detection")


@router.get("/custody-deadlines", summary="Open custody cases ordered by chargesheet deadline")
async def custody_deadlines(
    user: Officer,
    db: DbDep,
    district: str | None = None,
    only_due_within_days: int | None = Query(None, ge=0, le=90),
) -> dict:
    cases = [compute_deadline(c) for c in await CrimeRepository(db).custody_cases(OPEN_STATUSES)]
    if district:
        cases = [c for c in cases if c.district == district]
    if only_due_within_days is not None:
        cases = [c for c in cases if c.days_remaining <= only_due_within_days]
    cases.sort(key=lambda c: c.days_remaining)
    return {
        "total": len(cases),
        "overdue": sum(c.status == "overdue" for c in cases),
        "due_soon": sum(c.status == "due_soon" for c in cases),
        "items": [c.to_dict() for c in cases],
        "basis": "BNSS s.187(3): 90 days for offences punishable with death, life or 10+ years; 60 days otherwise.",
    }


@router.post("/custody-deadlines/scan", status_code=status.HTTP_202_ACCEPTED)
async def scan_custody(admin: Admin, redis: RedisDep) -> dict:
    return await queue_job(redis, admin, "app.workers.tasks.ml_tasks.run_custody_scan")


class SwarmRequest(BaseModel):
    days: int = Field(14, ge=3, le=60)
    runs: int = Field(300, ge=50, le=1000)
    patrols: int = Field(4, ge=0, le=12)
    freeze: bool = True


@router.get("/swarm/seeds", summary="Cases at the centre of the most-connected identifier networks")
async def swarm_seeds(user: Analyst, db: DbDep) -> list[dict]:
    return await swarm.seeds(db)


@router.post("/swarm/{crime_id}", summary="Swarm-simulate the next move of a case's linked pattern, with and without intervention")
@limiter.limit("20/minute")
async def swarm_simulate(request: Request, crime_id: uuid.UUID, body: SwarmRequest, user: Analyst, db: DbDep) -> dict:
    try:
        return await swarm.simulate(db, crime_id, days=body.days, runs=body.runs, patrols=body.patrols, freeze=body.freeze)
    except LookupError as exc:
        raise NotFoundError("Case not found") from exc
