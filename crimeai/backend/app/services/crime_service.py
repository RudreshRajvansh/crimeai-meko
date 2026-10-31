"""Crime use-cases: caching, case numbering, write-side effects."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.logging import get_logger
from app.db.redis import CacheManager
from app.repositories.crime_repository import CrimeRepository
from app.schemas.crime import (
    CrimeCreateRequest,
    CrimeFilterParams,
    CrimeListResponse,
    CrimeResponse,
    CrimeStatsResponse,
    CrimeUpdateRequest,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONFeatureProperties,
    GeoJSONPoint,
    NearbyFilterParams,
)
from app.services import entity_graph
from app.workers.dispatch import enqueue

logger = get_logger(__name__)

_STATS_TTL = 300
_AGGREGATE_TTL = 600
_CRIME_TTL = 120


class CrimeService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.repo = CrimeRepository(db)
        self.cache = CacheManager(redis, namespace="crimes")

    async def get_crime(self, crime_id: uuid.UUID) -> CrimeResponse:
        cached = await self.cache.get(f"crime:{crime_id}")
        if cached:
            return CrimeResponse(**cached)
        crime = await self.repo.get_by_id(crime_id)
        if crime is None:
            raise NotFoundError(f"Crime {crime_id} not found")
        response = CrimeResponse.model_validate(crime)
        await self.cache.set(f"crime:{crime_id}", response.model_dump(mode="json"), ttl=_CRIME_TTL)
        return response

    async def list_crimes(self, params: CrimeFilterParams) -> CrimeListResponse:
        criteria = params.model_dump(exclude={"limit", "offset"})
        crimes, total = await self.repo.list_crimes(limit=params.limit, offset=params.offset, **criteria)
        return CrimeListResponse(
            items=[CrimeResponse.model_validate(c) for c in crimes],
            total=total,
            limit=params.limit,
            offset=params.offset,
            has_more=(params.offset + params.limit) < total,
        )

    async def find_nearby(self, params: NearbyFilterParams) -> list[CrimeResponse]:
        crimes = await self.repo.find_within_radius(**params.model_dump())
        return [CrimeResponse.model_validate(c) for c in crimes]

    async def get_stats(
        self, from_date: datetime | None = None, to_date: datetime | None = None, city: str | None = None
    ) -> CrimeStatsResponse:
        key = f"stats:{city or 'all'}:{from_date}:{to_date}"
        cached = await self.cache.get(key)
        if cached:
            return CrimeStatsResponse(**cached)
        response = CrimeStatsResponse(**await self.repo.get_stats(from_date=from_date, to_date=to_date, city=city))
        await self.cache.set(key, response.model_dump(mode="json"), ttl=_STATS_TTL)
        return response

    async def get_hotspot_data(
        self, from_date: datetime | None = None, to_date: datetime | None = None, city: str | None = None
    ) -> list[dict]:
        key = f"hotspots:{city or 'all'}:{from_date}:{to_date}"
        cached = await self.cache.get(key)
        if cached is not None:
            return cached
        data = await self.repo.get_hotspot_data(from_date=from_date, to_date=to_date, city=city)
        await self.cache.set(key, data, ttl=_AGGREGATE_TTL)
        return data

    async def get_heatmap_points(
        self, from_date: datetime | None = None, to_date: datetime | None = None, crime_type: str | None = None
    ) -> list[dict]:
        key = f"heatmap:{crime_type or 'all'}:{from_date}:{to_date}"
        cached = await self.cache.get(key)
        if cached is not None:
            return cached
        points = await self.repo.get_heatmap_points(from_date=from_date, to_date=to_date, crime_type=crime_type)
        await self.cache.set(key, points, ttl=_AGGREGATE_TTL)
        return points

    async def export_geojson(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        crime_type: str | None = None,
        district: str | None = None,
    ) -> GeoJSONFeatureCollection:
        crimes = await self.repo.export_geojson(
            from_date=from_date, to_date=to_date, crime_type=crime_type, district=district
        )
        features = [
            GeoJSONFeature(
                geometry=GeoJSONPoint(coordinates=[c.longitude, c.latitude]),
                properties=GeoJSONFeatureProperties(
                    id=str(c.id),
                    crime_type=c.crime_type,
                    sub_type=c.sub_type,
                    severity=c.severity,
                    district=c.district,
                    city=c.city,
                    status=c.status,
                    occurred_at=c.occurred_at.isoformat(),
                    case_number=c.case_number,
                    risk_score=c.risk_score,
                ),
            )
            for c in crimes
        ]
        return GeoJSONFeatureCollection(
            features=features,
            metadata={
                "total": len(features),
                "exported_at": datetime.now(UTC).isoformat(),
                "filters": {
                    "crime_type": crime_type,
                    "district": district,
                    "from_date": from_date.isoformat() if from_date else None,
                    "to_date": to_date.isoformat() if to_date else None,
                },
            },
        )

    async def create_crime(self, data: CrimeCreateRequest, created_by: uuid.UUID) -> CrimeResponse:
        if data.case_number and await self.repo.get_by_case_number(data.case_number):
            raise AlreadyExistsError(f"Case number '{data.case_number}' already exists")

        description = (data.description or "").strip()
        if data.weapon_used:
            description += f" Weapon used: {data.weapon_used}."
        if data.num_suspects:
            description += f" Number of suspects: {data.num_suspects}."

        fields = data.model_dump(exclude={"weapon_used", "num_suspects", "description", "case_number"})
        try:
            crime = await self.repo.create(
                **fields,
                description=description.strip() or None,
                case_number=data.case_number or self._generate_case_number(),
            )
            if crime.description:
                await entity_graph.link_crime(self.db, crime.id, crime.description, occurred_at=crime.occurred_at)
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise AlreadyExistsError("Case number already exists") from exc

        logger.info("crime_created", crime_id=str(crime.id), crime_type=crime.crime_type, created_by=str(created_by))
        await self._after_write()
        enqueue("app.workers.tasks.ml_tasks.score_crime_risk", str(crime.id))
        enqueue("app.workers.tasks.ml_tasks.embed_crime", str(crime.id))
        return CrimeResponse.model_validate(crime)

    async def update_crime(self, crime_id: uuid.UUID, data: CrimeUpdateRequest) -> CrimeResponse:
        existing = await self.repo.get_by_id(crime_id)
        if existing is None:
            raise NotFoundError(f"Crime {crime_id} not found")
        changing_case_number = data.case_number and data.case_number != existing.case_number
        if changing_case_number and await self.repo.get_by_case_number(data.case_number):
            raise AlreadyExistsError(f"Case number '{data.case_number}' already in use")

        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return CrimeResponse.model_validate(existing)
        updated = await self.repo.update(crime_id, updates)
        await self.db.commit()

        await self.cache.delete(f"crime:{crime_id}")
        await self._after_write()
        if {"description", "crime_type", "sub_type", "district"} & updates.keys():
            enqueue("app.workers.tasks.ml_tasks.embed_crime", str(crime_id))
        logger.info("crime_updated", crime_id=str(crime_id), fields=sorted(updates))
        return CrimeResponse.model_validate(updated)

    async def delete_crime(self, crime_id: uuid.UUID) -> None:
        if not await self.repo.delete(crime_id):
            raise NotFoundError(f"Crime {crime_id} not found")
        await self.db.commit()
        await self.cache.delete(f"crime:{crime_id}")
        await self._after_write()
        logger.info("crime_deleted", crime_id=str(crime_id))

    @staticmethod
    def _generate_case_number() -> str:
        return f"CRM-{datetime.now(UTC).year}-{uuid.uuid4().hex[:10].upper()}"

    async def _after_write(self) -> None:
        for pattern in ("stats:*", "hotspots:*", "heatmap:*"):
            await self.cache.invalidate_pattern(pattern)
