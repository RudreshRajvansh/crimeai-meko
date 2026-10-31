"""
The cases behind an alert, so the UI can open them directly.

A link alert ("phone ... links 4 cases") is keyed by its identifier, a series
alert by its series id, and a custody alert points at one case. Resolving them
for a whole page of alerts takes one query per kind, not one per alert.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.crime import Crime
from app.models.entity import Entity, EntityMention

MAX_CASES_PER_ALERT = 24
_LINK_PREFIX = "link:"


def _case(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "case_number": row.case_number,
        "crime_type": row.crime_type,
        "district": row.district,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
    }


def _entity_id(alert: Alert) -> uuid.UUID | None:
    if alert.dedupe_key and alert.dedupe_key.startswith(_LINK_PREFIX):
        try:
            return uuid.UUID(alert.dedupe_key[len(_LINK_PREFIX):])
        except ValueError:
            return None
    return None


async def alert_context(db: AsyncSession, alerts: list[Alert]) -> dict[uuid.UUID, dict[str, Any]]:
    """Per alert: the linked cases (newest first), and the graph node to open them as a network."""
    columns = (Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.occurred_at)
    context: dict[uuid.UUID, dict[str, Any]] = {}

    by_entity = {a.id: eid for a in alerts if (eid := _entity_id(a))}
    if by_entity:
        rows = (await db.execute(
            select(EntityMention.entity_id, *columns)
            .join(Crime, Crime.id == EntityMention.crime_id)
            .where(EntityMention.entity_id.in_(set(by_entity.values())))
            .order_by(Crime.occurred_at.desc())
        )).all()
        kinds = dict((await db.execute(
            select(Entity.id, Entity.kind).where(Entity.id.in_(set(by_entity.values())))
        )).all())
        cases: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            cases[row.entity_id].append(_case(row))
        for alert_id, entity_id in by_entity.items():
            context[alert_id] = {
                "cases": cases[entity_id][:MAX_CASES_PER_ALERT],
                "graph_node": f"entity:{entity_id}",
                "entity_kind": kinds.get(entity_id),
            }

    by_series = {a.id: a.dedupe_key for a in alerts if a.alert_type == "crime_series" and a.dedupe_key}
    if by_series:
        rows = (await db.execute(
            select(Crime.series_id, *columns)
            .where(Crime.series_id.in_(set(by_series.values())))
            .order_by(Crime.occurred_at.desc())
        )).all()
        cases = defaultdict(list)
        for row in rows:
            cases[row.series_id].append(_case(row))
        for alert_id, series_id in by_series.items():
            context[alert_id] = {"cases": cases[series_id][:MAX_CASES_PER_ALERT], "graph_node": f"series:{series_id}"}

    single = {a.id: a.related_crime_id for a in alerts if a.related_crime_id and a.id not in context}
    if single:
        rows = {r.id: r for r in (await db.execute(select(*columns).where(Crime.id.in_(set(single.values()))))).all()}
        for alert_id, crime_id in single.items():
            if crime_id in rows:
                context[alert_id] = {"cases": [_case(rows[crime_id])], "graph_node": f"crime:{crime_id}"}

    return context
