"""Unit tests for patrol optimizer."""
from __future__ import annotations

from app.graph.algorithms.patrol_optimizer import (
    _coverage_route,
    _risk_weighted_route,
    _shortest_route,
    optimize_patrol,
)
from app.graph.algorithms.route_graph import GraphNode, RouteGraph


def _make_checkpoints(n: int = 6) -> list[dict]:
    """Create n evenly-spaced checkpoints around a central point."""
    import math
    center_lat, center_lng = 28.63, 77.22
    checkpoints = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        radius_deg = 0.02   # ~2km
        checkpoints.append({
            "id": f"cp-{i}",
            "lat": center_lat + radius_deg * math.cos(angle),
            "lng": center_lng + radius_deg * math.sin(angle),
            "label": f"Checkpoint {i}",
            "crime_count": (i + 1) * 3,
            "risk_score": (i + 1) * 10.0,
            "node_type": "checkpoint",
            "district": "TestDistrict",
        })
    return checkpoints


class TestOptimizePatrol:
    def test_returns_patrol_route_object(self):
        cps = _make_checkpoints(6)
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="shortest",
            num_checkpoints=4,
        )
        assert result is not None
        d = result.to_dict()
        assert "route_id" in d
        assert "checkpoints" in d
        assert "total_distance_km" in d
        assert "estimated_duration_minutes" in d

    def test_empty_checkpoints_returns_empty_route(self):
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=[],
            strategy="shortest",
        )
        assert result.total_distance_km == 0.0
        assert result.checkpoints == []

    def test_respects_num_checkpoints_limit(self):
        cps = _make_checkpoints(10)
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="shortest",
            num_checkpoints=3,
        )
        # START node + up to 3 checkpoints
        assert len(result.checkpoints) <= 4

    def test_risk_weighted_strategy_runs(self):
        cps = _make_checkpoints(6)
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="risk_weighted",
            num_checkpoints=5,
        )
        assert result.strategy == "risk_weighted"
        assert result.total_distance_km >= 0

    def test_coverage_strategy_runs(self):
        cps = _make_checkpoints(8)
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="coverage",
            num_checkpoints=5,
        )
        assert result.strategy == "coverage"
        assert result.coverage_radius_km >= 0

    def test_foot_patrol_slower_than_vehicle(self):
        cps = _make_checkpoints(6)
        vehicle = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="shortest",
            num_checkpoints=4,
            patrol_type="vehicle",
        )
        foot = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="shortest",
            num_checkpoints=4,
            patrol_type="foot",
        )
        assert foot.estimated_duration_minutes > vehicle.estimated_duration_minutes

    def test_generated_at_is_iso_string(self):
        cps = _make_checkpoints(4)
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="shortest",
        )
        from datetime import datetime
        # Should parse without error
        datetime.fromisoformat(result.generated_at)

    def test_route_id_is_uuid(self):
        import uuid
        cps = _make_checkpoints(4)
        result = optimize_patrol(
            start_lat=28.63, start_lng=77.22,
            district="TestDistrict",
            checkpoints=cps,
            strategy="shortest",
        )
        uuid.UUID(result.route_id)   # raises if invalid


class TestRouteStrategies:
    def _make_rg(self, n: int = 5) -> RouteGraph:
        import math
        rg = RouteGraph()
        rg.add_node(GraphNode("START", 28.63, 77.22, "Start", risk_score=0.0))
        for i in range(n):
            angle = 2 * math.pi * i / n
            rg.add_node(GraphNode(
                f"N{i}", 28.63 + 0.01 * math.cos(angle), 77.22 + 0.01 * math.sin(angle),
                f"Node {i}", risk_score=float(i * 15),
            ))
        rg.connect_all_within_radius(max_radius_km=10.0)
        return rg

    def test_risk_weighted_visits_start_first(self):
        rg = self._make_rg(5)
        route = _risk_weighted_route(rg, "START", max_stops=4)
        assert route[0] == "START"

    def test_coverage_visits_start_first(self):
        rg = self._make_rg(5)
        route = _coverage_route(rg, "START", max_stops=4)
        assert route[0] == "START"

    def test_shortest_visits_start_first(self):
        rg = self._make_rg(5)
        route = _shortest_route(rg, "START", max_stops=4)
        assert route[0] == "START"

    def test_no_duplicate_nodes_in_route(self):
        rg = self._make_rg(8)
        for strategy_fn in [_risk_weighted_route, _coverage_route, _shortest_route]:
            route = strategy_fn(rg, "START", max_stops=6)
            assert len(route) == len(set(route)), f"Duplicates in {strategy_fn.__name__}"


def test_start_position_is_not_counted_as_a_stop():
    """Regression: the start point was returned as stop 1, so asking for 5 checkpoints gave 6 stops."""
    from app.graph.algorithms.patrol_optimizer import optimize_patrol

    checkpoints = [
        {"id": f"CP-{i}", "lat": 28.60 + i * 0.01, "lng": 77.20 + i * 0.01, "label": f"Hotspot {i}",
         "crime_count": 10 - i, "risk_score": 50.0 - i, "node_type": "checkpoint", "district": "A"}
        for i in range(8)
    ]
    route = optimize_patrol(28.59, 77.19, "A", checkpoints, num_checkpoints=5).to_dict()
    assert len(route["checkpoints"]) == 5
    assert all(stop["node_type"] != "start" for stop in route["checkpoints"])
    assert [s["stop_number"] for s in route["checkpoints"]] == [1, 2, 3, 4, 5]
