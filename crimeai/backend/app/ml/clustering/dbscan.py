"""
DBSCAN Crime Clustering Module
-------------------------------
Uses scikit-learn DBSCAN with Haversine distance metric so that
eps is specified in kilometres, not degrees.

Returns cluster assignments that are then written back to the
crimes table (cluster_id column) and cached in Redis.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import DBSCAN

from app.core.config import settings
from app.core.exceptions import MLServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Earth radius in km — used for Haversine metric
_EARTH_RADIUS_KM = 6371.0


@dataclass
class ClusterResult:
    """Output of one DBSCAN run."""
    num_clusters: int
    noise_points: int
    total_points: int
    assignments: list[dict]          # [{"id": str, "cluster_id": int}]
    cluster_summaries: list[dict]    # per-cluster stats
    parameters: dict = field(default_factory=dict)

    @property
    def coverage_pct(self) -> float:
        """Percentage of points that were assigned to a cluster (not noise)."""
        if self.total_points == 0:
            return 0.0
        return round((self.total_points - self.noise_points) / self.total_points * 100, 2)


def _haversine_matrix(coords: np.ndarray) -> np.ndarray:
    """
    Compute pairwise Haversine distances (km) between lat/lng points.
    coords: shape (N, 2) in radians [lat, lng].
    Returns: (N, N) distance matrix in km.
    """
    lat = coords[:, 0]
    lng = coords[:, 1]
    dlat = lat[:, None] - lat[None, :]
    dlng = lng[:, None] - lng[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlng / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return _EARTH_RADIUS_KM * c


def run_dbscan(
    crime_records: list[dict],
    eps_km: float | None = None,
    min_samples: int | None = None,
    use_time_weight: bool = True,
) -> ClusterResult:
    """
    Run DBSCAN clustering on crime records.

    Parameters
    ----------
    crime_records : list of dicts with keys: id, lat, lng, crime_type, severity, occurred_at
    eps_km        : neighbourhood radius in kilometres (default from settings)
    min_samples   : minimum points to form a core point (default from settings)
    use_time_weight : if True, weight recent crimes more heavily

    Returns
    -------
    ClusterResult with per-crime assignments and per-cluster summaries
    """
    eps_km = eps_km or settings.DBSCAN_EPS
    min_samples = min_samples or settings.DBSCAN_MIN_SAMPLES

    if len(crime_records) < min_samples:
        logger.warning(
            "dbscan_insufficient_data",
            n_records=len(crime_records),
            min_samples=min_samples,
        )
        return ClusterResult(
            num_clusters=0,
            noise_points=len(crime_records),
            total_points=len(crime_records),
            assignments=[{"id": r["id"], "cluster_id": -1} for r in crime_records],
            cluster_summaries=[],
            parameters={"eps_km": eps_km, "min_samples": min_samples},
        )

    coords_deg = np.array([[r["lat"], r["lng"]] for r in crime_records])
    coords_rad = np.radians(coords_deg)

    # We don't change coordinates; instead we run DBSCAN on (lat, lng, time_weight)
    # using ball_tree + haversine (haversine only works on 2D so we skip time for now)

    # eps in radians: eps_km / earth_radius
    eps_rad = eps_km / _EARTH_RADIUS_KM

    try:
        db = DBSCAN(
            eps=eps_rad,
            min_samples=min_samples,
            algorithm="ball_tree",
            metric="haversine",
            n_jobs=-1,
        )
        labels = db.fit_predict(coords_rad)
    except Exception as exc:
        raise MLServiceError(f"DBSCAN failed: {exc}") from exc

    assignments = [
        {"id": crime_records[i]["id"], "cluster_id": int(labels[i])}
        for i in range(len(crime_records))
    ]

    unique_labels = set(labels)
    n_clusters = len(unique_labels - {-1})
    n_noise = int(np.sum(labels == -1))

    cluster_summaries = []
    for cluster_id in sorted(unique_labels - {-1}):
        mask = labels == cluster_id
        cluster_points = [crime_records[i] for i in range(len(crime_records)) if mask[i]]
        cluster_coords = coords_deg[mask]

        # Crime type frequency in cluster
        type_counts: dict[str, int] = {}
        severity_sum = 0
        for p in cluster_points:
            type_counts[p["crime_type"]] = type_counts.get(p["crime_type"], 0) + 1
            severity_sum += p.get("severity", 1)

        dominant_type = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]

        cluster_summaries.append({
            "cluster_id": int(cluster_id),
            "size": len(cluster_points),
            "centroid_lat": float(cluster_coords[:, 0].mean()),
            "centroid_lng": float(cluster_coords[:, 1].mean()),
            "dominant_crime_type": dominant_type,
            "crime_type_breakdown": type_counts,
            "avg_severity": round(severity_sum / len(cluster_points), 2),
            "bbox": {
                "min_lat": float(cluster_coords[:, 0].min()),
                "max_lat": float(cluster_coords[:, 0].max()),
                "min_lng": float(cluster_coords[:, 1].min()),
                "max_lng": float(cluster_coords[:, 1].max()),
            },
        })

    logger.info(
        "dbscan_complete",
        n_records=len(crime_records),
        n_clusters=n_clusters,
        n_noise=n_noise,
        eps_km=eps_km,
        min_samples=min_samples,
    )

    return ClusterResult(
        num_clusters=n_clusters,
        noise_points=n_noise,
        total_points=len(crime_records),
        assignments=assignments,
        cluster_summaries=cluster_summaries,
        parameters={"eps_km": eps_km, "min_samples": min_samples},
    )


def find_optimal_eps(
    crime_records: list[dict],
    min_samples: int = 3,
    k: int | None = None,
) -> float:
    """
    Estimate optimal eps using the k-distance graph elbow method.
    Returns the eps value at the 'elbow' of the sorted k-distances curve.

    Useful for adaptive clustering when crime density varies significantly.
    """
    if len(crime_records) < 10:
        return settings.DBSCAN_EPS

    k = k or min_samples
    coords_rad = np.radians([[r["lat"], r["lng"]] for r in crime_records])
    settings.DBSCAN_EPS / _EARTH_RADIUS_KM

    from sklearn.neighbors import NearestNeighbors
    nbrs = NearestNeighbors(
        n_neighbors=k,
        algorithm="ball_tree",
        metric="haversine",
    ).fit(coords_rad)
    distances, _ = nbrs.kneighbors(coords_rad)
    k_distances = np.sort(distances[:, -1])

    # Find elbow: point of maximum curvature
    n = len(k_distances)
    coords_2d = np.column_stack([np.arange(n), k_distances])
    # Vector from start to end
    line_vec = coords_2d[-1] - coords_2d[0]
    line_vec_norm = line_vec / np.linalg.norm(line_vec)
    # Distance of each point from the line
    vec_from_start = coords_2d - coords_2d[0]
    scalar_proj = np.dot(vec_from_start, line_vec_norm)
    proj = np.outer(scalar_proj, line_vec_norm)
    rejection = vec_from_start - proj
    distances_from_line = np.linalg.norm(rejection, axis=1)
    elbow_idx = int(np.argmax(distances_from_line))

    optimal_eps_rad = float(k_distances[elbow_idx])
    optimal_eps_km = optimal_eps_rad * _EARTH_RADIUS_KM

    logger.info(
        "optimal_eps_found",
        optimal_eps_km=round(optimal_eps_km, 4),
        elbow_idx=elbow_idx,
    )
    return max(0.1, min(optimal_eps_km, 10.0))  # Clamp between 100m and 10km
