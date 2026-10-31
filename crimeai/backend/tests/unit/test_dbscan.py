"""Unit tests for DBSCAN clustering module."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from app.ml.clustering.dbscan import (
    _haversine_matrix,
    find_optimal_eps,
    run_dbscan,
)


def _make_records(points: list[tuple[float, float]], crime_type: str = "theft") -> list[dict]:
    """Helper: create minimal crime records from lat/lng pairs."""
    return [
        {
            "id": f"crime-{i}",
            "lat": lat,
            "lng": lng,
            "crime_type": crime_type,
            "severity": 2,
            "occurred_at": datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
        }
        for i, (lat, lng) in enumerate(points)
    ]


class TestHaversineMatrix:
    def test_same_point_is_zero(self):
        coords = np.radians([[28.63, 77.22]])
        dist = _haversine_matrix(coords)
        assert dist[0, 0] == pytest.approx(0.0, abs=1e-6)

    def test_known_distance(self):
        """Delhi to Gurugram is ~30 km."""
        delhi = [28.6315, 77.2167]
        gurugram = [28.4595, 77.0266]
        coords = np.radians([delhi, gurugram])
        dist = _haversine_matrix(coords)
        assert 25 < dist[0, 1] < 35   # roughly 30 km

    def test_symmetric(self):
        coords = np.radians([[28.63, 77.22], [28.52, 77.18]])
        dist = _haversine_matrix(coords)
        assert dist[0, 1] == pytest.approx(dist[1, 0], rel=1e-6)


class TestRunDBSCAN:
    def test_insufficient_data_returns_noise(self):
        records = _make_records([(28.63, 77.22), (28.64, 77.23)])
        result = run_dbscan(records, eps_km=0.5, min_samples=3)
        assert result.num_clusters == 0
        assert result.noise_points == 2
        assert all(a["cluster_id"] == -1 for a in result.assignments)

    def test_tight_cluster_detected(self):
        """6 points within 200m of each other should form 1 cluster."""
        center_lat, center_lng = 28.6315, 77.2167
        points = [
            (center_lat + 0.001 * i, center_lng + 0.001 * i)
            for i in range(6)
        ]
        records = _make_records(points)
        result = run_dbscan(records, eps_km=1.0, min_samples=3)
        assert result.num_clusters >= 1

    def test_separated_clusters(self):
        """Two geographically separated groups should form 2 clusters."""
        # Group 1: near Connaught Place (Delhi)
        group1 = [(28.6315 + 0.0005 * i, 77.2167 + 0.0005 * i) for i in range(5)]
        # Group 2: near Dwarka (Delhi) — ~15km away
        group2 = [(28.5921 + 0.0005 * i, 77.0460 + 0.0005 * i) for i in range(5)]
        records = _make_records(group1 + group2)
        result = run_dbscan(records, eps_km=2.0, min_samples=3)
        assert result.num_clusters == 2

    def test_assignments_count_matches_input(self):
        points = [(28.63 + 0.001 * i, 77.22 + 0.001 * i) for i in range(8)]
        records = _make_records(points)
        result = run_dbscan(records, eps_km=1.0, min_samples=3)
        assert len(result.assignments) == 8

    def test_cluster_summary_contains_required_keys(self):
        points = [(28.63 + 0.0005 * i, 77.22 + 0.0005 * i) for i in range(6)]
        records = _make_records(points)
        result = run_dbscan(records, eps_km=1.0, min_samples=3)
        if result.cluster_summaries:
            summary = result.cluster_summaries[0]
            for key in ["cluster_id", "size", "centroid_lat", "centroid_lng",
                        "dominant_crime_type", "avg_severity", "bbox"]:
                assert key in summary, f"Missing key: {key}"

    def test_coverage_pct_valid_range(self):
        points = [(28.63 + 0.001 * i, 77.22 + 0.001 * i) for i in range(10)]
        records = _make_records(points)
        result = run_dbscan(records, eps_km=1.0, min_samples=3)
        assert 0.0 <= result.coverage_pct <= 100.0

    def test_parameters_stored_in_result(self):
        records = _make_records([(28.63, 77.22), (28.64, 77.23), (28.65, 77.24)])
        result = run_dbscan(records, eps_km=2.5, min_samples=2)
        assert result.parameters["eps_km"] == 2.5
        assert result.parameters["min_samples"] == 2


class TestFindOptimalEps:
    def test_insufficient_data_returns_default(self):
        records = _make_records([(28.63, 77.22), (28.64, 77.23)])
        eps = find_optimal_eps(records)
        from app.core.config import settings
        assert eps == settings.DBSCAN_EPS

    def test_returns_sensible_range(self):
        """Optimal eps should be between 0.1 and 10 km."""
        points = [(28.63 + 0.005 * i, 77.22 + 0.005 * i) for i in range(20)]
        records = _make_records(points)
        eps = find_optimal_eps(records, min_samples=3)
        assert 0.1 <= eps <= 10.0
