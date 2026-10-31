"""Persistence for alerts."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserRole
from app.models.alert import Alert
from app.services.alert_policy import visibility_clause


class AlertRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        return await self.db.get(Alert, alert_id)

    async def list_alerts(
        self,
        viewer_id: uuid.UUID,
        viewer_role: UserRole,
        is_resolved: bool | None = None,
        severity: str | None = None,
        alert_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Alert], int, int]:
        filters = []
        visibility = visibility_clause(viewer_id, viewer_role)
        if visibility is not None:
            filters.append(visibility)
        if is_resolved is not None:
            filters.append(Alert.is_resolved == is_resolved)
        if severity:
            filters.append(Alert.severity == severity)
        if alert_type:
            filters.append(Alert.alert_type == alert_type)
        where = and_(true(), *filters)

        total = (await self.db.execute(select(func.count(Alert.id)).where(where))).scalar_one()
        unread = (
            await self.db.execute(select(func.count(Alert.id)).where(where, Alert.is_read.is_(False)))
        ).scalar_one()
        rows = await self.db.execute(
            select(Alert).where(where).order_by(Alert.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total, unread

    async def create(self, **kwargs: Any) -> Alert:
        alert = Alert(**kwargs)
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)
        return alert

    async def exists_open(self, alert_type: str, dedupe_key: str, since: datetime) -> bool:
        query = select(func.count(Alert.id)).where(
            Alert.alert_type == alert_type,
            Alert.dedupe_key == dedupe_key,
            Alert.is_resolved.is_(False),
            Alert.created_at >= since,
        )
        return (await self.db.execute(query)).scalar_one() > 0

    async def mark_read(self, alert_id: uuid.UUID) -> None:
        await self.db.execute(update(Alert).where(Alert.id == alert_id).values(is_read=True))

    async def mark_resolved(self, alert_id: uuid.UUID, resolved_by: uuid.UUID) -> None:
        await self.db.execute(
            update(Alert)
            .where(Alert.id == alert_id)
            .values(is_resolved=True, is_read=True, resolved_by=resolved_by, resolved_at=func.now())
        )
