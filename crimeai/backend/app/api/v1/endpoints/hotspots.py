"""
Hotspot endpoints — cached heatmap and district-level aggregation data.
Powers the Crime Map page's heatmap and cluster overlays.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Viewer
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.crime_service import CrimeService

router = APIRouter()


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> CrimeService:
    return CrimeService(db=db, redis=redis)


@router.get(
    "/",
    summary="District-level crime hotspot aggregation",
)
async def get_hotspots(
    user: Viewer,
    service: Annotated[CrimeService, Depends(_get_service)],
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    city: str | None = Query(None),
) -> list[dict]:
    """
    Returns district + crime_type groups with:
    - count of crimes
    - centroid lat/lng
    - max severity in the group

    Used to render district-level choropleth / bubble map on the frontend.
    Data is Redis-cached for 10 minutes.
    """
    return await service.get_hotspot_data(
        from_date=from_date, to_date=to_date, city=city
    )


@router.get(
    "/heatmap",
    summary="Raw heatmap data points for Leaflet.heat",
)
async def get_heatmap(
    user: Viewer,
    service: Annotated[CrimeService, Depends(_get_service)],
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    crime_type: str | None = Query(None),
) -> list[dict]:
    """
    Returns [{lat, lng, weight}] for every crime.
    Weight is normalised severity (0.2–1.0).
    Data is Redis-cached for 10 minutes.
    """
    return await service.get_heatmap_points(
        from_date=from_date, to_date=to_date, crime_type=crime_type
    )
