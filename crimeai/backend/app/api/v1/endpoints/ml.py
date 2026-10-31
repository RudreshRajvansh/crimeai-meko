"""
ML outputs and job control.

Reads are served from the model registry. Training and scoring always run in
workers; these endpoints only enqueue them and let the caller poll.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Admin, Analyst, CurrentUser, Viewer
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.rate_limit import limiter
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.ml_service import MLService
from app.workers.dispatch import enqueue

router = APIRouter()
RedisDep = Annotated[Redis, Depends(get_redis)]
_TASK_OWNER_TTL = 86400


def _service(db: Annotated[AsyncSession, Depends(get_db)], redis: RedisDep) -> MLService:
    return MLService(db=db, redis=redis)


ServiceDep = Annotated[MLService, Depends(_service)]


async def queue_job(redis: Redis, user: CurrentUser, task: str, **kwargs) -> dict:
    task_id = enqueue(task, **kwargs)
    if task_id is None:
        return {"status": "queue_unavailable", "message": "Job queue is unavailable; the scheduled run will pick this up"}
    await redis.set(f"task:owner:{task_id}", str(user.user_id), ex=_TASK_OWNER_TTL)
    return {"status": "queued", "task_id": task_id, "status_url": f"{settings.API_V1_PREFIX}/ml/tasks/{task_id}"}


@router.post("/cluster", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_ML)
async def trigger_clustering(
    request: Request,
    user: Analyst,
    redis: RedisDep,
    eps_km: float | None = Query(None, ge=0.1, le=20.0),
    min_samples: int | None = Query(None, ge=2, le=50),
    auto_eps: bool = False,
    from_date: datetime | None = None,
) -> dict:
    return await queue_job(
        redis, user, "app.workers.tasks.ml_tasks.run_crime_clustering",
        eps_km=eps_km, min_samples=min_samples, auto_eps=auto_eps,
        from_date_iso=from_date.isoformat() if from_date else None,
    )


@router.get("/clusters")
async def get_clusters(user: Viewer, service: ServiceDep) -> dict:
    return await service.get_clusters()


@router.post("/hotspot-prediction", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_ML)
async def trigger_hotspot_pipeline(request: Request, user: Analyst, redis: RedisDep) -> dict:
    return await queue_job(redis, user, "app.workers.tasks.ml_tasks.refresh_forecasts", retrain=True)


@router.get("/hotspot-predictions", summary="Next 24 hours by shift and district")
async def get_hotspot_forecast(user: Viewer, service: ServiceDep) -> dict:
    return await service.get_hotspot_forecast()


@router.get("/risk-map", summary="Absolute 0-100 district risk index")
async def get_risk_map(user: Viewer, service: ServiceDep) -> dict:
    return await service.get_risk_map()


@router.post("/embed-crimes", status_code=status.HTTP_202_ACCEPTED)
async def batch_embed(admin: Admin, redis: RedisDep, limit: int = Query(1000, ge=1, le=10000)) -> dict:
    return await queue_job(redis, admin, "app.workers.tasks.ml_tasks.run_batch_embedding", limit=limit)


@router.get("/profile/{district}")
async def get_area_profile(
    district: str, user: Analyst, service: ServiceDep, lookback_days: int = Query(60, ge=7, le=365)
) -> dict:
    return await service.get_area_profile(district=district, lookback_days=lookback_days)


@router.get("/model-card", summary="Deployed model versions, evaluation and limitations")
async def model_card(user: Analyst, service: ServiceDep) -> dict:
    return await service.model_card()


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, user: Analyst, redis: RedisDep) -> dict:
    owner = await redis.get(f"task:owner:{task_id}")
    if owner is None or (owner != str(user.user_id) and not user.can(UserRole.ADMIN)):
        raise NotFoundError("Task not found")

    from celery.result import AsyncResult

    from app.workers.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    response: dict = {"task_id": task_id, "status": result.status}
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = "Job failed; see worker logs"
    return response
