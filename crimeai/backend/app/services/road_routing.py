"""
Road-network routing for patrol plans.

The patrol optimiser chooses and orders checkpoints using straight-line
distances; officers drive or walk on roads. This module asks an OSRM server for
the actual road path through the ordered stops (car or foot profile) and returns
its geometry, distance and travel time, so the map shows the route a unit would
really take.

Default server: the public FOSSGIS OSRM instance (routing.openstreetmap.de).
Coordinates of planned checkpoints leave the deployment when it is used, so an
operational deployment should point ROUTING_URL at a self-hosted OSRM built
from the state's OpenStreetMap extract. When routing is disabled or unreachable
the caller falls back to straight lines and says so.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis import CacheManager

logger = get_logger(__name__)

_PROFILES = {"vehicle": "car", "foot": "foot"}
_CACHE_TTL = 24 * 3600


def _cache_key(points: list[tuple[float, float]], profile: str) -> str:
    raw = json.dumps([profile, [(round(lat, 5), round(lng, 5)) for lat, lng in points]])
    return "road:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


async def road_path(points: list[tuple[float, float]], patrol_type: str, redis: Redis | None = None) -> dict[str, Any] | None:
    """Road geometry through `points` (lat, lng) in order, or None when routing is unavailable."""
    if not settings.ROUTING_ENABLED or len(points) < 2:
        return None
    profile = _PROFILES.get(patrol_type, "car")
    cache = CacheManager(redis, namespace="routing") if redis is not None else None
    key = _cache_key(points, profile)
    if cache and (cached := await cache.get(key)):
        return cached

    coords = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    url = f"{settings.ROUTING_URL.rstrip('/')}/routed-{profile}/route/v1/driving/{coords}"
    try:
        async with httpx.AsyncClient(timeout=settings.ROUTING_TIMEOUT_SECONDS,
                                     headers={"User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"}) as client:
            response = await client.get(url, params={"overview": "full", "geometries": "geojson", "steps": "false"})
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("road_routing_unavailable", error=str(exc)[:200])
        return None
    if response.status_code != 200 or body.get("code") != "Ok" or not body.get("routes"):
        logger.warning("road_routing_failed", status=response.status_code, code=body.get("code"))
        return None

    route = body["routes"][0]
    result = {
        "provider": "osrm",
        "profile": profile,
        # GeoJSON is [lng, lat]; Leaflet wants [lat, lng].
        "geometry": [[round(lat, 6), round(lng, 6)] for lng, lat in route["geometry"]["coordinates"]],
        "distance_km": round(route["distance"] / 1000, 2),
        "duration_min": round(route["duration"] / 60, 1),
        "legs": [{"distance_km": round(leg["distance"] / 1000, 2), "duration_min": round(leg["duration"] / 60, 1)}
                 for leg in route.get("legs", [])],
    }
    if cache:
        await cache.set(key, result, ttl=_CACHE_TTL)
    return result
