"""
Escape Route Analyzer
----------------------
Given a crime scene location, identifies the most probable escape
routes an offender might take based on:
  - Road network topology (simplified as a grid/graph of waypoints)
  - Proximity to exits (highways, transit stations)
  - Low-risk corridors (areas with minimal police presence / CCTV)
  - Distance-decay probability (closer paths are more likely)

Also generates an "intercept zone" — the set of nodes police
should reach quickly to cut off likely escape paths.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import networkx as nx

from app.core.logging import get_logger
from app.graph.algorithms.route_graph import (
    RouteGraph,
    build_crime_graph,
    haversine_km,
)

logger = get_logger(__name__)


@dataclass
class EscapeAnalysis:
    analysis_id: str
    crime_lat: float
    crime_lng: float
    district: str
    probable_routes: list[dict]        # ranked escape paths
    intercept_zones: list[dict]        # high-priority intercept points
    search_radius_km: float
    risk_surface: list[dict]           # risk heatmap for the area
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "crime_location": {
                "lat": self.crime_lat,
                "lng": self.crime_lng,
                "district": self.district,
            },
            "probable_routes": self.probable_routes,
            "intercept_zones": self.intercept_zones,
            "search_radius_km": self.search_radius_km,
            "risk_surface": self.risk_surface,
            "generated_at": self.generated_at,
        }


def analyze_escape_routes(
    crime_lat: float,
    crime_lng: float,
    district: str,
    nearby_crimes: list[dict],
    risk_scores: dict[str, float] | None = None,
    search_radius_km: float = 5.0,
    num_routes: int = 3,
) -> EscapeAnalysis:
    """
    Analyse likely escape routes from a crime scene.

    Parameters
    ----------
    crime_lat/lng   : exact crime location
    district        : district name
    nearby_crimes   : recent crimes in the area (from DB geo query)
    risk_scores     : district risk scores
    search_radius_km: how far to search for escape routes
    num_routes      : number of top escape routes to return

    Returns EscapeAnalysis with ranked routes and intercept zones.
    """
    risk_scores = risk_scores or {}

    # Each nearby crime location becomes a node in the escape network
    # The offender is likely to avoid high-crime (high-police) areas
    crime_scene_node = {
        "id": "CRIME_SCENE",
        "lat": crime_lat,
        "lng": crime_lng,
        "label": "Crime Scene",
        "crime_count": 1,
        "risk_score": 80.0,           # High risk at scene (police will arrive)
        "node_type": "crime_scene",
        "district": district,
    }

    waypoints = [crime_scene_node]

    # Generate synthetic waypoints in cardinal/diagonal directions
    # In production, replace with real road network nodes from OSM
    directions = [
        (0, 1), (0, -1), (1, 0), (-1, 0),     # N, S, E, W
        (1, 1), (1, -1), (-1, 1), (-1, -1),    # NE, SE, NW, SW
    ]
    lat_per_km = 1 / 111.0    # ~111 km per degree latitude
    lng_per_km = 1 / (111.0 * math.cos(math.radians(crime_lat)))

    for dist_km in [1.0, 2.0, 3.0, search_radius_km]:
        for i, (dlat_dir, dlng_dir) in enumerate(directions):
            node_lat = crime_lat + dlat_dir * dist_km * lat_per_km
            node_lng = crime_lng + dlng_dir * dist_km * lng_per_km
            node_id = f"WP_{dist_km}_{i}"

            # Risk at this waypoint: blend district risk + crime density from nearby crimes
            nearby_count = sum(
                1 for c in nearby_crimes
                if haversine_km(float(c.get("lat", 0)), float(c.get("lng", 0)),
                                node_lat, node_lng) <= 0.5
            )
            # High crime density = risky for offender (police patrols more likely)
            node_risk = min(100.0, nearby_count * 10 + risk_scores.get(district, 30.0))

            waypoints.append({
                "id": node_id,
                "lat": node_lat,
                "lng": node_lng,
                "label": f"Waypoint {node_id}",
                "crime_count": nearby_count,
                "risk_score": node_risk,
                "node_type": "waypoint",
                "district": district,
                "direction": f"{'N' if dlat_dir > 0 else 'S' if dlat_dir < 0 else ''}{'E' if dlng_dir > 0 else 'W' if dlng_dir < 0 else ''}",
                "distance_from_scene_km": dist_km,
            })

    rg = build_crime_graph(
        checkpoints=waypoints,
        risk_scores=risk_scores,
        max_connect_km=search_radius_km + 2,
    )

    probable_routes = _find_escape_paths(
        rg=rg,
        start_id="CRIME_SCENE",
        num_routes=num_routes,
        search_radius_km=search_radius_km,
    )

    intercept_zones = _identify_intercept_zones(
        probable_routes=probable_routes,
        rg=rg,
        num_zones=min(3, len(probable_routes)),
    )

    risk_surface = [
        {
            "lat": node.lat,
            "lng": node.lng,
            "risk": node.risk_score / 100.0,
            "label": node.label,
        }
        for node in rg.nodes.values()
        if node.node_id != "CRIME_SCENE"
    ]

    logger.info(
        "escape_analysis_complete",
        district=district,
        n_routes=len(probable_routes),
        n_intercept=len(intercept_zones),
        search_radius=search_radius_km,
    )

    return EscapeAnalysis(
        analysis_id=str(uuid.uuid4()),
        crime_lat=crime_lat,
        crime_lng=crime_lng,
        district=district,
        probable_routes=probable_routes,
        intercept_zones=intercept_zones,
        search_radius_km=search_radius_km,
        risk_surface=risk_surface,
        generated_at=datetime.now(UTC).isoformat(),
    )


def _find_escape_paths(
    rg: RouteGraph,
    start_id: str,
    num_routes: int,
    search_radius_km: float,
) -> list[dict]:
    """
    Find num_routes escape paths from start_id.
    Uses escape_cost edge weight (low-risk corridors preferred).
    """
    routes = []
    # Find all "exit" nodes (furthest nodes = likely escape destinations)
    exit_nodes = [
        nid for nid, node in rg.nodes.items()
        if nid != start_id
        and haversine_km(
            rg.nodes[start_id].lat, rg.nodes[start_id].lng,
            node.lat, node.lng,
        ) >= search_radius_km * 0.6
    ]

    if not exit_nodes:
        exit_nodes = [
            nid for nid in rg.nodes if nid != start_id
        ]

    # Rank exit nodes by escape attractiveness (low risk, far from scene)
    scored_exits = []
    for nid in exit_nodes:
        node = rg.nodes[nid]
        dist = haversine_km(
            rg.nodes[start_id].lat, rg.nodes[start_id].lng,
            node.lat, node.lng,
        )
        # Escape score: prefer far + low-risk exits
        score = dist * (1 - node.risk_score / 100.0)
        scored_exits.append((nid, score))

    scored_exits.sort(key=lambda x: x[1], reverse=True)
    top_exits = [nid for nid, _ in scored_exits[:num_routes * 2]]

    route_count = 0
    for target_id in top_exits:
        if route_count >= num_routes:
            break
        try:
            if nx.has_path(rg.graph, start_id, target_id):
                path_ids = nx.dijkstra_path(
                    rg.graph, start_id, target_id, weight="escape_cost"
                )
                # Compute path stats
                path_nodes = [rg.nodes[nid] for nid in path_ids if nid in rg.nodes]
                total_dist = sum(
                    haversine_km(
                        path_nodes[i].lat, path_nodes[i].lng,
                        path_nodes[i + 1].lat, path_nodes[i + 1].lng,
                    )
                    for i in range(len(path_nodes) - 1)
                )
                avg_risk = (
                    sum(n.risk_score for n in path_nodes) / len(path_nodes)
                    if path_nodes else 0
                )
                target_node = rg.nodes.get(target_id)

                # Probability: based on inverse risk and distance decay
                probability = max(0.05, (1 - avg_risk / 100.0) * math.exp(-total_dist / 3.0))

                routes.append({
                    "rank": route_count + 1,
                    "path_node_ids": path_ids,
                    "waypoints": [
                        {"lat": n.lat, "lng": n.lng, "label": n.label, "risk": n.risk_score}
                        for n in path_nodes
                    ],
                    "total_distance_km": round(total_dist, 3),
                    "avg_risk_score": round(avg_risk, 2),
                    "escape_probability": round(probability, 3),
                    "direction": target_node.metadata.get("direction", "") if target_node else "",
                    "estimated_time_minutes": round(total_dist / 0.833 * 60, 1),  # ~50 km/h
                })
                route_count += 1
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    # Sort by escape probability
    routes.sort(key=lambda r: r["escape_probability"], reverse=True)
    for i, r in enumerate(routes):
        r["rank"] = i + 1

    return routes


def _identify_intercept_zones(
    probable_routes: list[dict],
    rg: RouteGraph,
    num_zones: int,
) -> list[dict]:
    """
    Identify the best intercept points that cover the most escape routes.
    An intercept zone is a node that appears on multiple probable routes.
    """
    if not probable_routes:
        return []

    # Count node appearances across all routes
    node_appearances: dict[str, int] = {}
    for route in probable_routes:
        for nid in route.get("path_node_ids", []):
            if nid != "CRIME_SCENE":
                node_appearances[nid] = node_appearances.get(nid, 0) + 1

    # Rank nodes by appearances (most covered = best intercept)
    ranked = sorted(node_appearances.items(), key=lambda x: x[1], reverse=True)

    intercept_zones = []
    for nid, coverage in ranked[:num_zones]:
        node = rg.nodes.get(nid)
        if not node:
            continue
        intercept_zones.append({
            "node_id": nid,
            "lat": node.lat,
            "lng": node.lng,
            "label": node.label,
            "routes_covered": coverage,
            "total_routes": len(probable_routes),
            "coverage_pct": round(coverage / len(probable_routes) * 100, 1),
            "priority": "high" if coverage >= len(probable_routes) else "medium",
        })

    return intercept_zones
