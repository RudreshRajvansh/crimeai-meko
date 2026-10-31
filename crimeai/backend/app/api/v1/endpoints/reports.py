"""Generated reports."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Admin, Officer
from app.api.v1.endpoints.ml import queue_job
from app.core.exceptions import NotFoundError
from app.db.redis import get_redis
from app.db.session import get_db
from app.ml import registry
from app.services.briefing import BRIEFING
from app.services.storage import load_document

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/daily-briefing", summary="Latest daily station briefing (JSON)")
async def latest_briefing(user: Officer, db: DbDep) -> dict:
    artifact = await registry.latest(db, BRIEFING)
    if artifact is None:
        raise NotFoundError("No briefing generated yet")
    return {"version": artifact.version, "generated_at": artifact.created_at, "briefing": artifact.as_json()}


@router.get("/daily-briefing.pdf", summary="Latest daily station briefing (PDF)")
async def latest_briefing_pdf(user: Officer, db: DbDep) -> Response:
    artifact = await registry.latest(db, BRIEFING)
    if artifact is None or "pdf_url" not in artifact.metadata:
        raise NotFoundError("No briefing generated yet")
    pdf = await load_document(artifact.metadata["pdf_url"])
    filename = f"briefing-{artifact.as_json()['date']}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/daily-briefing", status_code=status.HTTP_202_ACCEPTED)
async def generate_briefing(admin: Admin, redis: Annotated[Redis, Depends(get_redis)]) -> dict:
    return await queue_job(redis, admin, "app.workers.tasks.report_tasks.generate_daily_briefing")
