"""Alerts: listing, manual creation and acknowledgement, all scoped by audience."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Admin, CurrentUser, Officer, Viewer
from app.core.exceptions import NotFoundError
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.alert import Alert
from app.realtime.broker import publish_alert
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertCreateRequest, AlertListResponse, AlertResponse
from app.services.alert_context import alert_context
from app.services.alert_policy import is_visible

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _with_context(alerts: list[Alert], user: CurrentUser, db: AsyncSession) -> list[AlertResponse]:
    """Linked cases are case data, so only roles that may read cases get them."""
    context = await alert_context(db, alerts) if user.can(UserRole.ANALYST) else {}
    return [AlertResponse.model_validate({**AlertResponse.model_validate(a).model_dump(), **context.get(a.id, {})})
            for a in alerts]


async def _visible_alert(alert_id: uuid.UUID, user: CurrentUser, db: AsyncSession) -> Alert:
    alert = await AlertRepository(db).get_by_id(alert_id)
    # Invisible and missing alerts are indistinguishable to the caller.
    if alert is None or not is_visible(alert.target_role, alert.assigned_to, user.user_id, user.role):
        raise NotFoundError("Alert not found")
    return alert


@router.get("/", response_model=AlertListResponse)
async def list_alerts(
    user: Viewer,
    db: DbDep,
    is_resolved: bool | None = Query(None),
    severity: str | None = Query(None),
    alert_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AlertListResponse:
    items, total, unread = await AlertRepository(db).list_alerts(
        viewer_id=user.user_id,
        viewer_role=user.role,
        is_resolved=is_resolved,
        severity=severity,
        alert_type=alert_type,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(items=await _with_context(items, user, db), total=total, unread_count=unread)


@router.post("/", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreateRequest,
    admin: Admin,
    db: DbDep,
    redis: Annotated[Redis, Depends(get_redis)],
) -> AlertResponse:
    alert = await AlertRepository(db).create(**body.model_dump())
    # Publish only once the row is durable, so clients never fetch an alert that does not exist.
    await db.commit()
    await publish_alert(redis, alert)
    return AlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: uuid.UUID, user: Viewer, db: DbDep) -> AlertResponse:
    return (await _with_context([await _visible_alert(alert_id, user, db)], user, db))[0]


@router.patch("/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(alert_id: uuid.UUID, user: Viewer, db: DbDep) -> None:
    await _visible_alert(alert_id, user, db)
    await AlertRepository(db).mark_read(alert_id)


@router.patch("/{alert_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_alert(alert_id: uuid.UUID, user: Officer, db: DbDep) -> None:
    await _visible_alert(alert_id, user, db)
    await AlertRepository(db).mark_resolved(alert_id, resolved_by=user.user_id)
