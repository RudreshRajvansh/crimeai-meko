"""Patrol routing, escape-route analysis and intervention simulation."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.redis import CacheManager
from app.graph.algorithms.escape_analyzer import analyze_escape_routes
from app.graph.algorithms.patrol_optimizer import _STOP_DURATION_MINUTES as STOP_DURATION_MINUTES
from app.graph.algorithms.patrol_optimizer import optimize_patrol
from app.graph.algorithms.simulation_engine import list_scenarios, run_simulation
from app.ml import registry
from app.repositories.crime_repository import CrimeRepository
from app.services.road_routing import road_path

_GRID_DEGREES = 0.01
_DEFAULT_DISTRICT_RISK = 30.0
# Bump when the shape or meaning of a cached patrol result changes.
_PATROL_CACHE_VERSION = 2


def build_checkpoints(crimes: list[dict], num_checkpoints: int) -> list[dict]:
    """Aggregate incidents into ~1 km grid cells and keep the busiest cells as patrol checkpoints."""
    grid: dict[tuple[float, float], list[dict]] = {}
    for crime in crimes:
        cell = (round(crime["lat"] / _GRID_DEGREES) * _GRID_DEGREES, round(crime["lng"] / _GRID_DEGREES) * _GRID_DEGREES)
        grid.setdefault(cell, []).append(crime)
    ranked = sorted(grid.items(), key=lambda item: len(item[1]), reverse=True)[:num_checkpoints]
    return [
        {
            "id": f"CP-{i:03d}",
            "lat": lat,
            "lng": lng,
            "label": f"Hotspot {i + 1}",
            "crime_count": len(cell),
            "risk_score": sum(c["risk_score"] for c in cell) / len(cell),
            "node_type": "checkpoint",
            "district": cell[0]["district"],
        }
        for i, ((lat, lng), cell) in enumerate(ranked)
    ]


class GraphService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.repo = CrimeRepository(db)
        self.redis = redis
        self.cache = CacheManager(redis, namespace="graph")

    async def _crimes(self, district: str | None, lookback_days: int) -> list[dict]:
        since = datetime.now(UTC) - timedelta(days=lookback_days)
        rows = await self.repo.get_records(since=since, district=district)
        return [
            {
                "id": str(r.id),
                "district": r.district or "Unknown",
                "crime_type": r.crime_type,
                "severity": r.severity,
                "lat": float(r.latitude),
                "lng": float(r.longitude),
                "risk_score": float(r.risk_score or 0),
                "occurred_at": r.occurred_at.isoformat(),
            }
            for r in rows
        ]

    async def _risk_scores(self) -> dict[str, float]:
        artifact = await registry.latest(self.db, registry.RISK_SCORES)
        if artifact is None:
            return {}
        return {district: data.get("score", _DEFAULT_DISTRICT_RISK) for district, data in artifact.as_json().items()}

    async def optimize_patrol_route(
        self, start_lat: float, start_lng: float, district: str,
        strategy: str = "risk_weighted", num_checkpoints: int = 5, patrol_type: str = "vehicle",
    ) -> dict:
        # Routes depend on where the unit starts; round to ~100 m so nearby requests share a cache entry.
        key = f"patrol:v{_PATROL_CACHE_VERSION}:{district}:{strategy}:{num_checkpoints}:{patrol_type}:{start_lat:.3f}:{start_lng:.3f}"
        if cached := await self.cache.get(key):
            return {**cached, "from_cache": True}

        crimes = await self._crimes(district, lookback_days=90)
        checkpoints = build_checkpoints(crimes, num_checkpoints * 3)
        risk = await self._risk_scores()
        route = await run_in_threadpool(
            optimize_patrol,
            start_lat=start_lat,
            start_lng=start_lng,
            district=district,
            checkpoints=checkpoints,
            strategy=strategy,
            num_checkpoints=num_checkpoints,
            patrol_type=patrol_type,
            risk_scores={district: risk.get(district, _DEFAULT_DISTRICT_RISK)},
        )
        result = route.to_dict()
        stops = [(start_lat, start_lng)] + [(c["lat"], c["lng"]) for c in result["checkpoints"]]
        result["road"] = await road_path(stops, patrol_type, self.redis)
        if result["road"]:
            # Straight-line figures understate real travel; report the road network's numbers.
            result["straight_line_km"] = result["total_distance_km"]
            result["total_distance_km"] = result["road"]["distance_km"]
            result["estimated_duration_minutes"] = round(
                result["road"]["duration_min"] + len(result["checkpoints"]) * STOP_DURATION_MINUTES, 1
            )
            for checkpoint, leg in zip(result["checkpoints"], result["road"]["legs"], strict=False):
                checkpoint["road_km_from_prev"] = leg["distance_km"]
                checkpoint["road_min_from_prev"] = leg["duration_min"]
        # A straight-line fallback is cached briefly so the road route is retried soon.
        await self.cache.set(key, result, ttl=900 if result["road"] else 60)
        return result

    async def analyze_escape(
        self, crime_lat: float, crime_lng: float, district: str, search_radius_km: float = 5.0, num_routes: int = 3,
    ) -> dict:
        nearby = await self.repo.find_within_radius(crime_lat, crime_lng, search_radius_km, limit=50)
        analysis = await run_in_threadpool(
            analyze_escape_routes,
            crime_lat=crime_lat,
            crime_lng=crime_lng,
            district=district,
            nearby_crimes=[{"lat": float(c.latitude), "lng": float(c.longitude), "district": c.district} for c in nearby],
            risk_scores=await self._risk_scores(),
            search_radius_km=search_radius_km,
            num_routes=num_routes,
        )
        return analysis.to_dict()

    async def run_what_if(self, scenario: str, district: str, parameters: dict, num_simulations: int = 200) -> dict:
        lookback_days = 60
        crimes = await self._crimes(district, lookback_days=lookback_days)
        if not crimes:
            return {"status": "insufficient_data", "message": f"No crime data found for district '{district}'"}
        result = await run_in_threadpool(
            run_simulation,
            scenario=scenario,
            district=district,
            parameters=parameters,
            crime_history=crimes,
            num_simulations=num_simulations,
            # Must match the query window, or the baseline rate is wrong by the ratio of the two.
            lookback_days=lookback_days,
        )
        return result.to_dict()

    async def get_scenario_list(self) -> list[dict]:
        return list_scenarios()
