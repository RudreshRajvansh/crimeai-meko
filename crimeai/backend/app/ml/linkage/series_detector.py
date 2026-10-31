"""
Crime series (linked-incident) detection.

Serial offenders, such as a chain-snatching pair working one arterial road or a
burglar targeting ground-floor flats, show up as clusters of incidents that
are close in space and time and share a modus operandi. Those incidents are
often filed at different police stations, so nobody sees the pattern until
much later. This module links them automatically.

Narrative similarity uses multilingual embeddings, calibrated for the
language gap (see `language_gap`) so a Hindi FIR and an English FIR of the
same modus operandi link as readily as two English ones.

Two incidents are linked when all of the following hold:
  * same crime type
  * within `radius_km` of each other
  * within `window_days` of each other
  * narrative similarity >= `min_similarity` (sentence embeddings when
    available, TF-IDF otherwise)

"Similar" is judged against the crime type's own background: a pair must be
more alike than `background_quantile` of all pairs of that type (and at least
`min_similarity`). Short narratives of one crime type are naturally alike, so a
fixed cut-off alone links ordinary, unrelated incidents.

Linked incidents are merged with union-find. Because single links chain
(A~B and B~C pulls in an unrelated C), each component is then pruned: members
whose average similarity to the rest falls below the threshold are dropped
until the series is cohesive. Components of at least `min_size` incidents
become candidate series. Each series is reported with
its cohesion, spatial footprint, cadence and an expected next-incident window.
Analysts confirm or reject a series; the system only proposes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import BallTree

_EARTH_RADIUS_KM = 6371.0088
_MAX_ADAPTIVE_THRESHOLD = 0.95
_BACKGROUND_SAMPLE = 20_000
_MIN_BACKGROUND_PAIRS = 30  # fewer unrelated pairs than this: fall back to every pair


@dataclass(slots=True)
class Incident:
    id: str
    crime_type: str
    lat: float
    lng: float
    occurred_at: datetime
    text: str = ""
    district: str | None = None
    embedding: np.ndarray | None = None
    language: str = "en"


@dataclass(slots=True)
class CrimeSeries:
    series_id: str
    crime_type: str
    incident_ids: list[str]
    districts: list[str]
    first_seen: datetime
    last_seen: datetime
    centroid: tuple[float, float]
    radius_km: float
    cohesion: float
    median_gap_days: float | None
    next_window: tuple[datetime, datetime] | None
    key_terms: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "crime_type": self.crime_type,
            "size": len(self.incident_ids),
            "incident_ids": self.incident_ids,
            "districts": self.districts,
            "cross_jurisdiction": len(self.districts) > 1,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "centroid": {"lat": self.centroid[0], "lng": self.centroid[1]},
            "radius_km": round(self.radius_km, 3),
            "cohesion": round(self.cohesion, 3),
            "median_gap_days": None if self.median_gap_days is None else round(self.median_gap_days, 2),
            "next_window": None if self.next_window is None else {
                "from": self.next_window[0].isoformat(), "to": self.next_window[1].isoformat(),
            },
            "key_terms": self.key_terms,
            "languages": self.languages,
            "cross_language": len(self.languages) > 1,
        }


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lng2 - lng1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * _EARTH_RADIUS_KM * np.arcsin(np.sqrt(a)))


def _similarity_matrix(incidents: list[Incident]) -> tuple[np.ndarray, TfidfVectorizer | None, Any]:
    if all(i.embedding is not None for i in incidents):
        vectors = np.vstack([i.embedding for i in incidents]).astype(float)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.where(norms == 0, 1, norms)
        return vectors @ vectors.T, None, None
    texts = [i.text or i.crime_type for i in incidents]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english", sublinear_tf=True)
    matrix = vectorizer.fit_transform(texts)
    return (matrix @ matrix.T).toarray(), vectorizer, matrix


_MIN_PAIRS_FOR_GAP = 20
_MAX_LANGUAGE_GAP = 0.15


def language_gap(similarity: np.ndarray, languages: list[str]) -> float:
    """
    How much lower multilingual embeddings score a cross-language pair than a same-language pair of the
    same crime type, estimated from the data (difference of medians). Adding it back to cross-language
    pairs puts a Hindi-English match on the same scale as an English-English one.
    """
    langs = np.asarray(languages)
    rows, cols = np.triu_indices(len(langs), k=1)
    same = langs[rows] == langs[cols]
    if same.sum() < _MIN_PAIRS_FOR_GAP or (~same).sum() < _MIN_PAIRS_FOR_GAP:
        return 0.0
    values = similarity[rows, cols]
    gap = float(np.median(values[same]) - np.median(values[~same]))
    return float(min(max(gap, 0.0), _MAX_LANGUAGE_GAP))


def calibrate_for_language(similarity: np.ndarray, languages: list[str]) -> tuple[np.ndarray, float]:
    gap = language_gap(similarity, languages)
    if gap == 0.0:
        return similarity, 0.0
    langs = np.asarray(languages)
    cross = langs[:, None] != langs[None, :]
    return np.minimum(similarity + gap * cross, 1.0), gap


def adaptive_threshold(
    similarity: np.ndarray, floor: float, quantile: float, rng_seed: int = 0, background: np.ndarray | None = None,
    fallback: float | None = None,
) -> float:
    """
    Similarity a pair must reach to be unusual for this crime type.

    `background` marks the pairs that could never share a series (too far apart in place or time). They show
    how alike two unrelated incidents of this type read; measuring on every pair instead would let a large
    series raise its own bar with its near-identical members and shut out a member written another way.
    """
    n = similarity.shape[0]
    if n < 3:
        return floor
    rows, cols = np.triu_indices(n, k=1)
    if background is not None:
        keep = background[rows, cols]
        if keep.sum() >= _MIN_BACKGROUND_PAIRS:
            rows, cols = rows[keep], cols[keep]
        elif fallback is not None:
            return fallback
    if len(rows) > _BACKGROUND_SAMPLE:
        pick = np.random.default_rng(rng_seed).choice(len(rows), _BACKGROUND_SAMPLE, replace=False)
        rows, cols = rows[pick], cols[pick]
    background = float(np.quantile(similarity[rows, cols], quantile))
    return float(min(max(floor, background), _MAX_ADAPTIVE_THRESHOLD))


def _prune(members: list[int], similarity: np.ndarray, bar: np.ndarray, min_size: int) -> list[int]:
    """Drop the least cohesive member until everyone is, on average, as similar to the rest as its pairs require."""
    members = list(members)
    while len(members) >= min_size:
        sub = similarity[np.ix_(members, members)] - bar[np.ix_(members, members)]
        margin = (sub.sum(axis=1) - np.diag(sub)) / (len(members) - 1)
        worst = int(np.argmin(margin))
        if margin[worst] >= -1e-6:
            return members
        members.pop(worst)
    return []


def _series_id(member_ids: list[str]) -> str:
    # Anchored on the earliest member so the ID stays stable as a series grows.
    return "SER-" + hashlib.sha1(member_ids[0].encode(), usedforsecurity=False).hexdigest()[:10].upper()


def _key_terms(vectorizer: TfidfVectorizer | None, matrix: Any, members: list[int], top_n: int = 6) -> list[str]:
    if vectorizer is None:
        return []
    weights = np.asarray(matrix[members].mean(axis=0)).ravel()
    vocab = vectorizer.get_feature_names_out()
    return [vocab[i] for i in weights.argsort()[::-1][:top_n] if weights[i] > 0]


def detect_series(
    incidents: list[Incident],
    radius_km: float = 3.0,
    window_days: int = 21,
    min_similarity: float = 0.72,
    min_size: int = 3,
    background_quantile: float = 0.99,
) -> list[CrimeSeries]:
    by_type: dict[str, list[Incident]] = {}
    for incident in incidents:
        by_type.setdefault(incident.crime_type, []).append(incident)

    found: list[CrimeSeries] = []
    for crime_type, group in by_type.items():
        if len(group) < min_size:
            continue
        group.sort(key=lambda i: i.occurred_at)
        coords = np.radians([[i.lat, i.lng] for i in group])
        neighbours = BallTree(coords, metric="haversine").query_radius(coords, r=radius_km / _EARTH_RADIUS_KM)
        similarity, vectorizer, tfidf = _similarity_matrix(group)
        if vectorizer is None:
            similarity, _ = calibrate_for_language(similarity, [i.language for i in group])
        window = timedelta(days=window_days)
        near = np.zeros((len(group), len(group)), dtype=bool)
        for i, idx in enumerate(neighbours):
            near[i, idx] = True
        stamps = np.array([i.occurred_at.timestamp() for i in group])
        candidates = near & (np.abs(stamps[:, None] - stamps[None, :]) <= window.total_seconds())
        threshold = adaptive_threshold(similarity, min_similarity, background_quantile, background=~candidates)
        # A Hindi-English pair is judged against other Hindi-English pairs: embeddings score cross-language
        # pairs on their own scale, so a bar drawn from same-language pairs would shut those reports out.
        langs = np.asarray([i.language for i in group])
        cross = langs[:, None] != langs[None, :]
        cross_threshold = adaptive_threshold(
            similarity, min_similarity, background_quantile, background=~candidates & cross, fallback=threshold,
        )
        bar = np.where(cross, cross_threshold, threshold)

        uf = _UnionFind(len(group))
        for i, near in enumerate(neighbours):
            for j in near:
                if j <= i:
                    continue
                if abs(group[j].occurred_at - group[i].occurred_at) <= window and similarity[i, j] >= bar[i, j] - 1e-6:
                    uf.union(i, j)

        components: dict[int, list[int]] = {}
        for idx in range(len(group)):
            components.setdefault(uf.find(idx), []).append(idx)

        for component in components.values():
            members = _prune(component, similarity, bar, min_size) if len(component) >= min_size else []
            if len(members) < min_size:
                continue
            members.sort(key=lambda k: group[k].occurred_at)
            member_incidents = [group[k] for k in members]
            lat = float(np.mean([m.lat for m in member_incidents]))
            lng = float(np.mean([m.lng for m in member_incidents]))
            pair_sims = [similarity[a, b] for x, a in enumerate(members) for b in members[x + 1:]]
            times = [m.occurred_at for m in member_incidents]
            gaps = [(b - a).total_seconds() / 86400 for a, b in pairwise(times)]
            median_gap = float(np.median(gaps)) if gaps else None
            next_window = None
            if median_gap is not None and median_gap > 0:
                spread = max(float(np.std(gaps)) if len(gaps) > 1 else median_gap / 2, 1.0)
                expected = times[-1] + timedelta(days=median_gap)
                next_window = (expected - timedelta(days=spread), expected + timedelta(days=spread))

            found.append(CrimeSeries(
                series_id=_series_id([m.id for m in member_incidents]),
                crime_type=crime_type,
                incident_ids=[m.id for m in member_incidents],
                districts=sorted({m.district for m in member_incidents if m.district}),
                first_seen=times[0],
                last_seen=times[-1],
                centroid=(lat, lng),
                radius_km=max(_haversine_km(lat, lng, m.lat, m.lng) for m in member_incidents),
                cohesion=float(np.mean(pair_sims)) if pair_sims else 1.0,
                median_gap_days=median_gap,
                next_window=next_window,
                key_terms=_key_terms(vectorizer, tfidf, members),
                languages=sorted({m.language for m in member_incidents}),
            ))

    return sorted(found, key=lambda s: (s.last_seen, len(s.incident_ids)), reverse=True)
