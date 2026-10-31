"""
Crime records.

Access model: aggregates are visible to every signed-in role, individual
records need analyst or above, writes need police, deletion needs admin.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Admin, Analyst, Officer, Viewer
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.redis import get_redis
from app.db.session import get_db
from app.schemas.crime import (
    CrimeCreateRequest,
    CrimeFilterParams,
    CrimeListResponse,
    CrimeResponse,
    CrimeStatsResponse,
    CrimeUpdateRequest,
    NearbyFilterParams,
)
from app.services.audit_service import record_audit
from app.services.crime_service import CrimeService
from app.services.dossier import build_dossier

router = APIRouter()


def _service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> CrimeService:
    return CrimeService(db=db, redis=redis)


ServiceDep = Annotated[CrimeService, Depends(_service)]


@router.get("/", response_model=CrimeListResponse)
async def list_crimes(
    user: Analyst,
    service: ServiceDep,
    params: Annotated[CrimeFilterParams, Query()],
) -> CrimeListResponse:
    return await service.list_crimes(params)


@router.get("/stats", response_model=CrimeStatsResponse)
async def crime_stats(
    user: Viewer,
    service: ServiceDep,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    city: str | None = None,
) -> CrimeStatsResponse:
    return await service.get_stats(from_date=from_date, to_date=to_date, city=city)


@router.get("/heatmap")
async def heatmap(
    user: Viewer,
    service: ServiceDep,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    crime_type: str | None = None,
) -> list[dict]:
    return await service.get_heatmap_points(from_date=from_date, to_date=to_date, crime_type=crime_type)


@router.get("/nearby", response_model=list[CrimeResponse])
async def crimes_nearby(user: Analyst, service: ServiceDep, params: Annotated[NearbyFilterParams, Query()]) -> list[CrimeResponse]:
    return await service.find_nearby(params)


@router.get("/export/geojson", response_class=JSONResponse)
async def export_geojson(
    request: Request,
    user: Analyst,
    service: ServiceDep,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    crime_type: str | None = None,
    district: str | None = None,
) -> JSONResponse:
    collection = await service.export_geojson(
        from_date=from_date, to_date=to_date, crime_type=crime_type, district=district
    )
    await record_audit(
        db, request, user, action="crimes.export", resource_type="crime",
        metadata={"rows": len(collection.features), "district": district, "crime_type": crime_type},
    )
    return JSONResponse(
        content=collection.model_dump(mode="json"),
        headers={"Content-Disposition": 'attachment; filename="crimes.geojson"'},
        media_type="application/geo+json",
    )


@router.get("/{crime_id}/dossier", summary="Everything known about one case on a single screen")
async def crime_dossier(crime_id: uuid.UUID, request: Request, user: Analyst,
                        db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    result = await build_dossier(db, crime_id, user)
    await record_audit(db, request, user, action="crime.dossier", resource_type="crime", resource_id=str(crime_id))
    return result


@router.get("/{crime_id}", response_model=CrimeResponse)
async def get_crime(crime_id: uuid.UUID, user: Analyst, service: ServiceDep) -> CrimeResponse:
    return await service.get_crime(crime_id)


@router.post("/", response_model=CrimeResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def create_crime(request: Request, body: CrimeCreateRequest, user: Officer, service: ServiceDep) -> CrimeResponse:
    return await service.create_crime(body, created_by=user.user_id)


@router.patch("/{crime_id}", response_model=CrimeResponse)
async def update_crime(crime_id: uuid.UUID, body: CrimeUpdateRequest, user: Officer, service: ServiceDep) -> CrimeResponse:
    return await service.update_crime(crime_id, body)


@router.delete("/{crime_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_crime(crime_id: uuid.UUID, user: Admin, service: ServiceDep) -> None:
    await service.delete_crime(crime_id)

