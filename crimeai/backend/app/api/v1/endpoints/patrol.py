"""Patrol route optimisation and escape-route analysis."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Analyst, Officer
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.graph_service import GraphService

router = APIRouter()


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> GraphService:
    return GraphService(db=db, redis=redis)


class PatrolRequest(BaseModel):
    start_lat: float = Field(..., ge=-90, le=90, description="Officer's starting latitude")
    start_lng: float = Field(..., ge=-180, le=180, description="Officer's starting longitude")
    district: str = Field(..., min_length=2, max_length=100)
    num_checkpoints: int = Field(default=5, ge=2, le=20)
    strategy: str = Field(
        default="risk_weighted",
        pattern="^(risk_weighted|coverage|shortest)$",
        description="risk_weighted: prioritise high-risk areas | coverage: maximise spread | shortest: minimum distance",
    )
    patrol_type: str = Field(
        default="vehicle",
        pattern="^(vehicle|foot)$",
    )


class EscapeRequest(BaseModel):
    crime_lat: float = Field(..., ge=-90, le=90)
    crime_lng: float = Field(..., ge=-180, le=180)
    district: str = Field(..., min_length=2, max_length=100)
    search_radius_km: float = Field(default=5.0, ge=0.5, le=20.0)
    num_routes: int = Field(default=3, ge=1, le=5)


@router.post(
    "/optimize",
    summary="Generate optimized patrol route (Police+)",
)
@limiter.limit(settings.RATE_LIMIT_ML)
async def optimize_patrol(
    request: Request,
    body: PatrolRequest,
    user: Officer,
    service: Annotated[GraphService, Depends(_get_service)],
) -> dict:
    """
    Generates an optimised patrol route using one of three strategies:

    - **risk_weighted**: Visits highest-risk crime hotspots first —
      best for targeted suppression of active crime areas.
    - **coverage**: Maximises geographic spread across the district —
      best for general deterrence patrol.
    - **shortest**: Nearest-neighbour TSP — minimises travel time,
      best when shift time is limited.

    Results are cached for 15 minutes per district+strategy combination.
    """
    return await service.optimize_patrol_route(
        start_lat=body.start_lat,
        start_lng=body.start_lng,
        district=body.district,
        strategy=body.strategy,
        num_checkpoints=body.num_checkpoints,
        patrol_type=body.patrol_type,
    )


@router.post(
    "/escape-analysis",
    summary="Analyse escape routes from crime scene (Analyst+)",
)
async def analyze_escape(
    body: EscapeRequest,
    user: Analyst,
    service: Annotated[GraphService, Depends(_get_service)],
) -> dict:
    """
    Identifies probable escape routes from a crime location and
    recommends intercept zones for rapid police deployment.

    Returns:
    - **probable_routes**: ranked escape paths with probability scores
    - **intercept_zones**: priority interception points covering most routes
    - **risk_surface**: node-level risk heatmap for the search area
    """
    return await service.analyze_escape(
        crime_lat=body.crime_lat,
        crime_lng=body.crime_lng,
        district=body.district,
        search_radius_km=body.search_radius_km,
        num_routes=body.num_routes,
    )

