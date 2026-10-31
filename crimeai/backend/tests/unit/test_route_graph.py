"""Unit tests for the route graph module."""
from __future__ import annotations

import pytest

from app.graph.algorithms.route_graph import (
    GraphNode,
    RouteGraph,
    build_crime_graph,
    haversine_km,
)


class TestHaversineKm:
    def test_same_point_is_zero(self):
        assert haversine_km(28.63, 77.22, 28.63, 77.22) == pytest.approx(0.0, abs=1e-6)

    def test_delhi_to_gurugram_approx_30km(self):
        dist = haversine_km(28.6315, 77.2167, 28.4595, 77.0266)
        assert 25 < dist < 35

    def test_symmetric(self):
        d1 = haversine_km(28.63, 77.22, 28.52, 77.18)
        d2 = haversine_km(28.52, 77.18, 28.63, 77.22)
        assert d1 == pytest.approx(d2, rel=1e-6)

    def test_one_degree_lat_approx_111km(self):
        dist = haversine_km(0.0, 0.0, 1.0, 0.0)
        assert 110 < dist < 112


class TestRouteGraph:
    def _make_rg_with_nodes(self) -> RouteGraph:
        rg = RouteGraph()
        rg.add_node(GraphNode("A", 28.63, 77.22, "Alpha", risk_score=20.0))
        rg.add_node(GraphNode("B", 28.64, 77.23, "Beta",  risk_score=60.0))
        rg.add_node(GraphNode("C", 28.65, 77.24, "Gamma", risk_score=80.0))
        return rg

    def test_add_nodes(self):
        rg = self._make_rg_with_nodes()
        assert len(rg.nodes) == 3
        assert "A" in rg.nodes

    def test_add_edge_bidirectional(self):
        rg = self._make_rg_with_nodes()
        rg.add_edge("A", "B")
        assert rg.graph.has_edge("A", "B")
        assert rg.graph.has_edge("B", "A")   # bidirectional

    def test_add_edge_unidirectional(self):
        rg = self._make_rg_with_nodes()
        rg.add_edge("A", "B", bidirectional=False)
        assert rg.graph.has_edge("A", "B")
        assert not rg.graph.has_edge("B", "A")

    def test_edge_has_distance(self):
        rg = self._make_rg_with_nodes()
        rg.add_edge("A", "B")
        edge_data = rg.graph["A"]["B"]
        assert "distance_km" in edge_data
        assert edge_data["distance_km"] > 0

    def test_high_risk_edge_has_higher_patrol_cost(self):
        rg = RouteGraph()
        # Low risk node pair
        rg.add_node(GraphNode("L1", 28.63, 77.22, "Low1", risk_score=5.0))
        rg.add_node(GraphNode("L2", 28.6301, 77.2201, "Low2", risk_score=5.0))
        rg.add_edge("L1", "L2")
        # High risk node pair (same distance)
        rg.add_node(GraphNode("H1", 28.64, 77.23, "High1", risk_score=90.0))
        rg.add_node(GraphNode("H2", 28.6401, 77.2301, "High2", risk_score=90.0))
        rg.add_edge("H1", "H2")

        low_cost = rg.graph["L1"]["L2"]["patrol_cost"]
        high_cost = rg.graph["H1"]["H2"]["patrol_cost"]
        # High risk patrol cost should be higher (more important to not skip)
        assert high_cost > low_cost

    def test_connect_all_within_radius(self):
        rg = self._make_rg_with_nodes()
        edges = rg.connect_all_within_radius(max_radius_km=50.0)
        # 3 nodes → 3 pairs → 6 directed edges
        assert edges == 6

    def test_connect_all_excludes_far_nodes(self):
        rg = RouteGraph()
        rg.add_node(GraphNode("Near", 28.63, 77.22, "Near"))
        rg.add_node(GraphNode("Far", 29.00, 78.00, "Far"))   # ~100km away
        rg.connect_all_within_radius(max_radius_km=5.0)
        assert not rg.graph.has_edge("Near", "Far")

    def test_to_dict_structure(self):
        rg = self._make_rg_with_nodes()
        rg.connect_all_within_radius(50.0)
        d = rg.to_dict()
        assert "num_nodes" in d
        assert "num_edges" in d
        assert "nodes" in d
        assert "edges" in d
        assert d["num_nodes"] == 3


class TestBuildCrimeGraph:
    def test_builds_from_checkpoints(self):
        checkpoints = [
            {"id": f"cp{i}", "lat": 28.63 + i * 0.01, "lng": 77.22 + i * 0.01,
             "label": f"CP{i}", "crime_count": i, "district": "TestDistrict"}
            for i in range(5)
        ]
        rg = build_crime_graph(checkpoints, max_connect_km=10.0)
        assert len(rg.nodes) == 5

    def test_risk_scores_applied(self):
        checkpoints = [
            {"id": "A", "lat": 28.63, "lng": 77.22, "label": "A",
             "crime_count": 5, "district": "HighRisk"},
        ]
        rg = build_crime_graph(
            checkpoints,
            risk_scores={"HighRisk": 85.0},
            max_connect_km=5.0,
        )
        assert rg.nodes["A"].risk_score == pytest.approx(85.0)

    def test_empty_checkpoints_returns_empty_graph(self):
        rg = build_crime_graph([], max_connect_km=5.0)
        assert len(rg.nodes) == 0
