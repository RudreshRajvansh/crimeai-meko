"""
Crime-Aware Route Graph
-----------------------
Builds a weighted directed graph from crime data and geographic points.
Node weights represent risk scores; edge weights are distance + risk penalty.

Used by:
  - Patrol optimizer (find safest high-coverage route)
  - Escape analysis (find likely escape paths from crime scene)
  - Route risk assessor (score any given path)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from app.core.logging import get_logger

logger = get_logger(__name__)

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance between two GPS points in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


@dataclass
class GraphNode:
    node_id: str
    lat: float
    lng: float
    label: str = ""
    risk_score: float = 0.0          # 0–100
    crime_count: int = 0
    node_type: str = "waypoint"      # checkpoint | hotspot | start | end | waypoint
    metadata: dict = field(default_factory=dict)


@dataclass
class RouteGraph:
    """Weighted directed graph for crime-aware routing."""
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    nodes: dict[str, GraphNode] = field(default_factory=dict)

    def add_node(self, node: GraphNode, risk_weight: float = 1.0) -> None:
        self.nodes[node.node_id] = node
        self.graph.add_node(
            node.node_id,
            lat=node.lat,
            lng=node.lng,
            label=node.label,
            risk_score=node.risk_score,
            crime_count=node.crime_count,
            node_type=node.node_type,
            risk_weight=risk_weight,
        )

    def add_edge(self, from_id: str, to_id: str, bidirectional: bool = True) -> None:
        """Add edge(s) with distance + risk-weighted cost."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return
        n1 = self.nodes[from_id]
        n2 = self.nodes[to_id]
        dist = haversine_km(n1.lat, n1.lng, n2.lat, n2.lng)

        # Edge cost: distance + risk penalty (higher risk = more costly for patrol)
        # For escape analysis we invert: low risk = preferred escape route
        avg_risk = (n1.risk_score + n2.risk_score) / 2.0
        patrol_cost = dist * (1 + avg_risk / 100.0)   # risk makes edge more costly to skip
        escape_cost = dist * (1 + (100 - avg_risk) / 100.0)   # low-risk = preferred escape

        self.graph.add_edge(
            from_id, to_id,
            distance_km=dist,
            patrol_cost=patrol_cost,
            escape_cost=escape_cost,
        )
        if bidirectional:
            self.graph.add_edge(
                to_id, from_id,
                distance_km=dist,
                patrol_cost=patrol_cost,
                escape_cost=escape_cost,
            )

    def connect_all_within_radius(self, max_radius_km: float = 3.0) -> int:
        """Connect every pair of nodes within max_radius_km. Returns edge count added."""
        node_list = list(self.nodes.values())
        edges_added = 0
        for i, n1 in enumerate(node_list):
            for n2 in node_list[i + 1:]:
                dist = haversine_km(n1.lat, n1.lng, n2.lat, n2.lng)
                if dist <= max_radius_km:
                    self.add_edge(n1.node_id, n2.node_id)
                    edges_added += 2
        return edges_added

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "nodes": [
                {
                    "id": nid,
                    **dict(data.items()),
                }
                for nid, data in self.graph.nodes(data=True)
            ],
            "edges": [
                {
                    "from": u,
                    "to": v,
                    "distance_km": round(data.get("distance_km", 0), 3),
                    "patrol_cost": round(data.get("patrol_cost", 0), 3),
                }
                for u, v, data in self.graph.edges(data=True)
            ],
        }


def build_crime_graph(
    checkpoints: list[dict],
    risk_scores: dict[str, float] | None = None,
    max_connect_km: float = 5.0,
) -> RouteGraph:
    """
    Build a RouteGraph from a list of checkpoint dicts.

    checkpoints: [{"id": str, "lat": float, "lng": float, "label": str,
                   "crime_count": int, "district": str}]
    risk_scores: {district: score_0_to_100} — from risk_scorer module
    """
    rg = RouteGraph()
    risk_scores = risk_scores or {}

    for cp in checkpoints:
        district = cp.get("district", "")
        risk = risk_scores.get(district, cp.get("risk_score", 0.0))
        node = GraphNode(
            node_id=cp["id"],
            lat=float(cp["lat"]),
            lng=float(cp["lng"]),
            label=cp.get("label", cp["id"]),
            risk_score=float(risk),
            crime_count=int(cp.get("crime_count", 0)),
            node_type=cp.get("node_type", "waypoint"),
            metadata={"district": district},
        )
        rg.add_node(node)

    edges = rg.connect_all_within_radius(max_connect_km)
    logger.info(
        "route_graph_built",
        n_nodes=len(rg.nodes),
        n_edges=edges,
        max_connect_km=max_connect_km,
    )
    return rg
