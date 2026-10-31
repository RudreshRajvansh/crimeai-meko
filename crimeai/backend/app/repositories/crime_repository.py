"""Persistence and spatial/aggregate queries for crimes."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import and_, cast, extract, func, literal_column, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import Crime

HEATMAP_POINT_LIMIT = 20_000
# Bare `geography` (no typmod) so the expression matches the functional index on (geom::geography).
_GEOGRAPHY = Geography(geometry_type=None, spatial_index=False)
GEOJSON_EXPORT_LIMIT = 10_000


def _point(latitude: float, longitude: float):
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def _window(from_date: datetime | None, to_date: datetime | None) -> list:
    filters = []
    if from_date:
        filters.append(Crime.occurred_at >= from_date)
    if to_date:
        filters.append(Crime.occurred_at <= to_date)
    return filters


class CrimeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, crime_id: uuid.UUID) -> Crime | None:
        return await self.db.get(Crime, crime_id)

    async def get_by_case_number(self, case_number: str) -> Crime | None:
        result = await self.db.execute(select(Crime).where(Crime.case_number == case_number))
        return result.scalar_one_or_none()

    async def list_crimes(self, limit: int = 100, offset: int = 0, **criteria: Any) -> tuple[list[Crime], int]:
        where = and_(true(), *self._filters(**criteria))
        total = (await self.db.execute(select(func.count(Crime.id)).where(where))).scalar_one()
        rows = await self.db.execute(
            select(Crime).where(where).order_by(Crime.occurred_at.desc(), Crime.id).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total

    @staticmethod
    def _filters(
        crime_type: str | None = None,
        district: str | None = None,
        city: str | None = None,
        status: str | None = None,
        severity_min: int | None = None,
        severity_max: int | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        assigned_officer_id: uuid.UUID | None = None,
        cluster_id: int | None = None,
        series_id: str | None = None,
    ) -> list:
        filters = _window(from_date, to_date)
        equals = {
            Crime.crime_type: crime_type,
            Crime.district: district,
            Crime.city: city,
            Crime.status: status,
            Crime.assigned_officer_id: assigned_officer_id,
            Crime.cluster_id: cluster_id,
            Crime.series_id: series_id,
        }
        filters.extend(column == value for column, value in equals.items() if value is not None)
        if severity_min is not None:
            filters.append(Crime.severity >= severity_min)
        if severity_max is not None:
            filters.append(Crime.severity <= severity_max)
        return filters

    async def find_within_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        crime_type: str | None = None,
        limit: int = 100,
    ) -> list[Crime]:
        # Matches the functional GiST index on (geom::geography), so this is an index scan in metres.
        geog = cast(Crime.geom, _GEOGRAPHY)
        point = cast(_point(latitude, longitude), _GEOGRAPHY)
        query = select(Crime).where(func.ST_DWithin(geog, point, radius_km * 1000))
        if crime_type:
            query = query.where(Crime.crime_type == crime_type)
        query = query.order_by(func.ST_Distance(geog, point)).limit(limit)
        return list((await self.db.execute(query)).scalars().all())

    async def get_all_coordinates(
        self, from_date: datetime | None = None, to_date: datetime | None = None
    ) -> list[dict]:
        query = select(
            Crime.id, Crime.latitude, Crime.longitude, Crime.crime_type, Crime.severity, Crime.occurred_at
        ).where(and_(true(), *_window(from_date, to_date)))
        return [
            {
                "id": str(r.id),
                "lat": float(r.latitude),
                "lng": float(r.longitude),
                "crime_type": r.crime_type,
                "severity": r.severity,
                "occurred_at": r.occurred_at.isoformat(),
            }
            for r in (await self.db.execute(query)).all()
        ]

    async def get_records(
        self,
        since: datetime | None = None,
        district: str | None = None,
        columns: tuple = (),
    ) -> list[Any]:
        base = (Crime.id, Crime.district, Crime.crime_type, Crime.severity, Crime.occurred_at,
                Crime.latitude, Crime.longitude, Crime.risk_score)
        query = select(*(base + columns))
        if since:
            query = query.where(Crime.occurred_at >= since)
        if district:
            query = query.where(Crime.district == district)
        return list((await self.db.execute(query)).all())

    async def get_stats(
        self, from_date: datetime | None = None, to_date: datetime | None = None, city: str | None = None
    ) -> dict:
        filters = _window(from_date, to_date)
        if city:
            filters.append(Crime.city == city)
        where = and_(true(), *filters)

        async def grouped(column):
            rows = await self.db.execute(
                select(column, func.count(Crime.id).label("cnt")).where(where).group_by(column)
                .order_by(func.count(Crime.id).desc())
            )
            return rows.all()

        by_type = await grouped(Crime.crime_type)
        by_district = await grouped(Crime.district)
        by_status = await grouped(Crime.status)
        by_severity = await grouped(Crime.severity)

        month = func.date_trunc(literal_column("'month'"), Crime.occurred_at).label("month")
        latest_months = (
            select(month, func.count(Crime.id).label("cnt")).where(where).group_by(month)
            .order_by(month.desc()).limit(12).subquery()
        )
        month_rows = (await self.db.execute(select(latest_months).order_by(latest_months.c.month))).all()

        span = (
            await self.db.execute(
                select(func.count(Crime.id), func.min(Crime.occurred_at), func.max(Crime.occurred_at)).where(where)
            )
        ).one()
        total, first_seen, last_seen = span
        start = from_date or first_seen
        end = to_date or last_seen
        days = max(((end - start).total_seconds() / 86400) if start and end else 1, 1)

        hour = extract("hour", Crime.occurred_at)
        hour_row = (
            await self.db.execute(
                select(hour.label("hr"), func.count(Crime.id)).where(where).group_by(hour)
                .order_by(func.count(Crime.id).desc()).limit(1)
            )
        ).first()

        return {
            "total_crimes": total,
            "by_type": {r[0]: r.cnt for r in by_type},
            "by_district": {(r[0] or "Unknown"): r.cnt for r in by_district},
            "by_status": {r[0]: r.cnt for r in by_status},
            "by_severity": {str(r[0]): r.cnt for r in sorted(by_severity, key=lambda r: r[0])},
            "by_month": [
                {"year": r.month.year, "month": r.month.month, "count": r.cnt} for r in month_rows
            ],
            "avg_daily_crimes": round(total / days, 2) if total else 0.0,
            "most_active_hour": int(hour_row.hr) if hour_row else 0,
        }

    async def get_hotspot_data(
        self, from_date: datetime | None = None, to_date: datetime | None = None, city: str | None = None
    ) -> list[dict]:
        filters = _window(from_date, to_date)
        if city:
            filters.append(Crime.city == city)
        query = (
            select(
                Crime.district,
                Crime.crime_type,
                func.count(Crime.id).label("count"),
                func.avg(Crime.latitude).label("avg_lat"),
                func.avg(Crime.longitude).label("avg_lng"),
                func.max(Crime.severity).label("max_severity"),
            )
            .where(and_(true(), *filters))
            .group_by(Crime.district, Crime.crime_type)
            .order_by(func.count(Crime.id).desc())
        )
        return [
            {
                "district": r.district or "Unknown",
                "crime_type": r.crime_type,
                "count": r.count,
                "lat": float(r.avg_lat or 0),
                "lng": float(r.avg_lng or 0),
                "max_severity": r.max_severity,
            }
            for r in (await self.db.execute(query)).all()
        ]

    async def get_heatmap_points(
        self, from_date: datetime | None = None, to_date: datetime | None = None, crime_type: str | None = None
    ) -> list[dict]:
        filters = _window(from_date or datetime.now(UTC) - timedelta(days=365), to_date)
        if crime_type:
            filters.append(Crime.crime_type == crime_type)
        query = (
            select(Crime.latitude, Crime.longitude, Crime.severity)
            .where(and_(true(), *filters))
            .order_by(Crime.occurred_at.desc())
            .limit(HEATMAP_POINT_LIMIT)
        )
        return [
            {"lat": float(r.latitude), "lng": float(r.longitude), "weight": float(r.severity) / 5.0}
            for r in (await self.db.execute(query)).all()
        ]

    async def create(self, latitude: float, longitude: float, **fields: Any) -> Crime:
        crime = Crime(latitude=latitude, longitude=longitude, geom=_point(latitude, longitude), **fields)
        self.db.add(crime)
        await self.db.flush()
        await self.db.refresh(crime)
        return crime

    async def update(self, crime_id: uuid.UUID, updates: dict[str, Any]) -> Crime | None:
        current = await self.get_by_id(crime_id)
        if current is None:
            return None
        if "latitude" in updates or "longitude" in updates:
            updates["geom"] = _point(updates.get("latitude", current.latitude), updates.get("longitude", current.longitude))
        await self.db.execute(update(Crime).where(Crime.id == crime_id).values(**updates))
        await self.db.refresh(current)
        return current

    async def delete(self, crime_id: uuid.UUID) -> bool:
        crime = await self.get_by_id(crime_id)
        if crime is None:
            return False
        await self.db.delete(crime)
        await self.db.flush()
        return True

    async def bulk_update_clusters(self, assignments: list[dict]) -> int:
        if not assignments:
            return 0
        await self.db.execute(update(Crime).values(cluster_id=None).where(Crime.cluster_id.is_not(None)))
        await self.db.execute(
            update(Crime),
            [{"id": uuid.UUID(row["id"]), "cluster_id": row["cluster_id"]} for row in assignments],
        )
        return len(assignments)

    async def assign_series(self, assignments: dict[str, str]) -> int:
        if not assignments:
            return 0
        await self.db.execute(
            update(Crime),
            [{"id": uuid.UUID(crime_id), "series_id": series_id} for crime_id, series_id in assignments.items()],
        )
        return len(assignments)

    async def update_risk_score(self, crime_id: uuid.UUID, risk_score: float) -> None:
        await self.db.execute(update(Crime).where(Crime.id == crime_id).values(risk_score=risk_score))

    async def custody_cases(self, open_statuses: tuple[str, ...]) -> list[Crime]:
        query = select(Crime).where(
            Crime.accused_arrested_at.is_not(None),
            Crime.chargesheet_filed_at.is_(None),
            Crime.status.in_(open_statuses),
        ).order_by(Crime.accused_arrested_at)
        return list((await self.db.execute(query)).scalars().all())

    async def export_geojson(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        crime_type: str | None = None,
        district: str | None = None,
    ) -> list[Crime]:
        filters = _window(from_date, to_date)
        if crime_type:
            filters.append(Crime.crime_type == crime_type)
        if district:
            filters.append(Crime.district == district)
        query = (
            select(Crime).where(and_(true(), *filters)).order_by(Crime.occurred_at.desc()).limit(GEOJSON_EXPORT_LIMIT)
        )
        return list((await self.db.execute(query)).scalars().all())
