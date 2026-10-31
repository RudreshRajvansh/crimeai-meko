"""
Patrol Route Optimizer
-----------------------
Given a set of crime hotspot checkpoints and a start position,
compute the optimal patrol route using one of three strategies:

  1. risk_weighted  — Prioritise visiting highest-risk areas first
                      (greedy nearest-neighbour by risk-adjusted cost)
  2. coverage       — Maximise geographic coverage (spread across district)
  3. shortest       — Minimum total distance (nearest-neighbour TSP)

All three use the same RouteGraph structure but different edge weights.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.graph.algorithms.route_graph import (
    RouteGraph,
    build_crime_graph,
    haversine_km,
)

logger = get_logger(__name__)

# Average patrol speed assumptions
_PATROL_SPEED_KMH = 25.0           # Vehicle patrol
_FOOT_PATROL_SPEED_KMH = 5.0       # Foot patrol
_STOP_DURATION_MINUTES = 10.0      # Time spent at each checkpoint


@dataclass
class PatrolRoute:
    """Output of the patrol optimizer."""
    route_id: str
    strategy: str
    district: str
    checkpoints: list[dict]          # ordered list of stops
    total_distance_km: float
    estimated_duration_minutes: float
    total_risk_covered: float        # sum of risk scores at visited nodes
    coverage_radius_km: float
    generated_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "strategy": self.strategy,
            "district": self.district,
            "checkpoints": self.checkpoints,
            "total_distance_km": round(self.total_distance_km, 3),
            "estimated_duration_minutes": round(self.estimated_duration_minutes, 1),
            "total_risk_covered": round(self.total_risk_covered, 2),
            "coverage_radius_km": self.coverage_radius_km,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
        }


def optimize_patrol(
    start_lat: float,
    start_lng: float,
    district: str,
    checkpoints: list[dict],
    strategy: str = "risk_weighted",
    num_checkpoints: int = 5,
    patrol_type: str = "vehicle",
    risk_scores: dict[str, float] | None = None,
) -> PatrolRoute:
    """
    Generate an optimised patrol route.

    Parameters
    ----------
    start_lat/lng    : officer starting position
    district         : district name for labelling
    checkpoints      : candidate stops [{id, lat, lng, label, crime_count, risk_score}]
    strategy         : 'risk_weighted' | 'coverage' | 'shortest'
    num_checkpoints  : how many stops to include
    patrol_type      : 'vehicle' | 'foot'
    risk_scores      : district risk scores from risk_scorer module

    Returns PatrolRoute with ordered stops and metadata.
    """
    if not checkpoints:
        return _empty_route(start_lat, start_lng, district, strategy)

    # Add start node
    start_node = {
        "id": "START",
        "lat": start_lat,
        "lng": start_lng,
        "label": "Patrol Start",
        "crime_count": 0,
        "risk_score": 0.0,
        "node_type": "start",
        "district": district,
    }
    all_points = [start_node, *checkpoints]

    # Build graph
    rg = build_crime_graph(
        checkpoints=all_points,
        risk_scores=risk_scores,
        max_connect_km=20.0,   # allow connections up to 20km for sparse areas
    )

    # Select route using chosen strategy
    if strategy == "risk_weighted":
        ordered_ids = _risk_weighted_route(rg, "START", num_checkpoints)
    elif strategy == "coverage":
        ordered_ids = _coverage_route(rg, "START", num_checkpoints)
    else:  # shortest
        ordered_ids = _shortest_route(rg, "START", num_checkpoints)

    # Build output
    route_stops = []
    total_dist = 0.0
    total_risk = 0.0
    prev_lat, prev_lng = start_lat, start_lng

    for node_id in ordered_ids:
        node = rg.nodes.get(node_id)
        if not node or node_id == "START":
            # The start position is where the unit begins, not a checkpoint to visit.
            continue
        dist_from_prev = haversine_km(prev_lat, prev_lng, node.lat, node.lng)
        total_dist += dist_from_prev
        total_risk += node.risk_score
        prev_lat, prev_lng = node.lat, node.lng

        route_stops.append({
            "stop_number": len(route_stops) + 1,
            "node_id": node_id,
            "label": node.label,
            "lat": node.lat,
            "lng": node.lng,
            "risk_score": node.risk_score,
            "crime_count": node.crime_count,
            "node_type": node.node_type,
            "distance_from_prev_km": round(dist_from_prev, 3),
            "cumulative_distance_km": round(total_dist, 3),
        })

    # Time estimate
    speed = _PATROL_SPEED_KMH if patrol_type == "vehicle" else _FOOT_PATROL_SPEED_KMH
    travel_minutes = (total_dist / speed) * 60
    stop_minutes = len(route_stops) * _STOP_DURATION_MINUTES
    total_minutes = travel_minutes + stop_minutes

    # Geographic coverage radius (average distance from centroid)
    if route_stops:
        lats = [s["lat"] for s in route_stops]
        lngs = [s["lng"] for s in route_stops]
        centroid_lat = sum(lats) / len(lats)
        centroid_lng = sum(lngs) / len(lngs)
        coverage_radius = max(
            haversine_km(centroid_lat, centroid_lng, s["lat"], s["lng"])
            for s in route_stops
        )
    else:
        coverage_radius = 0.0

    logger.info(
        "patrol_route_optimized",
        strategy=strategy,
        district=district,
        n_stops=len(route_stops),
        total_distance_km=round(total_dist, 2),
        estimated_minutes=round(total_minutes, 1),
    )

    return PatrolRoute(
        route_id=str(uuid.uuid4()),
        strategy=strategy,
        district=district,
        checkpoints=route_stops,
        total_distance_km=total_dist,
        estimated_duration_minutes=total_minutes,
        total_risk_covered=total_risk,
        coverage_radius_km=round(coverage_radius, 3),
        generated_at=datetime.now(UTC).isoformat(),
        metadata={
            "patrol_type": patrol_type,
            "speed_kmh": speed,
            "graph_nodes": rg.graph.number_of_nodes(),
        },
    )

def _risk_weighted_route(
    rg: RouteGraph, start_id: str, max_stops: int
) -> list[str]:
    """
    Greedy nearest-neighbour prioritising high-risk nodes.
    Cost = patrol_cost on edge (distance × risk penalty).
    Nodes with higher risk are visited preferentially.
    """
    visited = [start_id]
    remaining = [nid for nid in rg.nodes if nid != start_id]

    while remaining and len(visited) - 1 < max_stops:
        current = visited[-1]
        best_id = None
        best_score = float("inf")

        for candidate in remaining:
            if rg.graph.has_edge(current, candidate):
                edge_data = rg.graph[current][candidate]
                patrol_cost = edge_data.get("patrol_cost", float("inf"))
                candidate_risk = rg.nodes[candidate].risk_score
                # Score: low cost is good, but penalise skipping high-risk nodes
                score = patrol_cost / (1 + candidate_risk / 100.0)
            else:
                # Not directly connected — use haversine as fallback
                n1, n2 = rg.nodes[current], rg.nodes[candidate]
                dist = haversine_km(n1.lat, n1.lng, n2.lat, n2.lng)
                score = dist * 10   # heavy penalty for unconnected nodes

            if score < best_score:
                best_score = score
                best_id = candidate

        if best_id:
            visited.append(best_id)
            remaining.remove(best_id)
        else:
            break

    return visited


def _coverage_route(
    rg: RouteGraph, start_id: str, max_stops: int
) -> list[str]:
    """
    Maximise geographic spread — next stop is always the furthest
    unvisited node from the current position.
    Ensures patrol covers the whole district, not just one cluster.
    """
    visited = [start_id]
    remaining = [nid for nid in rg.nodes if nid != start_id]

    while remaining and len(visited) - 1 < max_stops:
        current = visited[-1]
        n_current = rg.nodes[current]
        best_id = None
        best_dist = -1.0

        for candidate in remaining:
            n_cand = rg.nodes[candidate]
            haversine_km(n_current.lat, n_current.lng, n_cand.lat, n_cand.lng)
            # Also consider distance from ALL visited nodes (maximise total spread)
            min_dist_from_visited = min(
                haversine_km(rg.nodes[v].lat, rg.nodes[v].lng, n_cand.lat, n_cand.lng)
                for v in visited
            )
            coverage_score = min_dist_from_visited  # Penalise clustering

            if coverage_score > best_dist:
                best_dist = coverage_score
                best_id = candidate

        if best_id:
            visited.append(best_id)
            remaining.remove(best_id)
        else:
            break

    return visited


def _shortest_route(
    rg: RouteGraph, start_id: str, max_stops: int
) -> list[str]:
    """
    Nearest-neighbour TSP approximation.
    Minimises total travel distance — fastest route ignoring risk.
    """
    visited = [start_id]
    remaining = [nid for nid in rg.nodes if nid != start_id]

    while remaining and len(visited) - 1 < max_stops:
        current = visited[-1]
        n_current = rg.nodes[current]
        best_id = None
        best_dist = float("inf")

        for candidate in remaining:
            n_cand = rg.nodes[candidate]
            dist = haversine_km(n_current.lat, n_current.lng, n_cand.lat, n_cand.lng)
            if dist < best_dist:
                best_dist = dist
                best_id = candidate

        if best_id:
            visited.append(best_id)
            remaining.remove(best_id)
        else:
            break

    return visited


def _empty_route(lat: float, lng: float, district: str, strategy: str) -> PatrolRoute:
    return PatrolRoute(
        route_id=str(uuid.uuid4()),
        strategy=strategy,
        district=district,
        checkpoints=[],
        total_distance_km=0.0,
        estimated_duration_minutes=0.0,
        total_risk_covered=0.0,
        coverage_radius_km=0.0,
        generated_at=datetime.now(UTC).isoformat(),
        metadata={"warning": "No checkpoints provided"},
    )
