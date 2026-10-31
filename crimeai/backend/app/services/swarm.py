"""
Swarm simulation of a case's next move.

Seeded from one case and everything the link graph ties to it (shared vehicles,
phones, UPI IDs, accounts, or the same series), the engine spawns offender
agents anchored on the identifiers they use, police units on the densest past
locations, and plays several hundred futures hour by hour. Each future draws:

- how many hits a day, from the cluster's own tempo (Poisson, with recent cases
  weighted up when the pace is accelerating);
- when, from the cluster's hour-of-day profile;
- where, from a near-repeat kernel around past locations, recent ones favoured;
- which identifier is used, in proportion to how often each appeared.

The same random stream is replayed with and without the analyst's intervention
(patrol units, freezing the money trail) so the difference is the intervention,
not noise. It forecasts places and windows for a linked pattern, never a person.
"""
from __future__ import annotations

import math
import uuid
from collections import Counter, deque
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import Crime
from app.models.entity import Entity, EntityMention

STREET_TYPES = {"chain_snatching", "robbery", "burglary", "theft", "vehicle_theft", "assault"}
MONEY_KINDS = {"upi", "account"}
_MAX_CASES = 60
_PATROL_RADIUS_KM = 0.9
_PATROL_CATCH = 0.55       # chance a unit on shift within range stops a street hit
_FREEZE_BLOCK = 0.85       # chance a frozen account or UPI ID stops the money landing
_SAMPLE_RUNS = 3


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dy = (lat2 - lat1) * 111.0
    dx = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


async def _cluster(db: AsyncSession, crime_id: uuid.UUID) -> tuple[list[Crime], dict[uuid.UUID, list[Entity]], str]:
    """The seed case plus every case two hops away through shared identifiers or its series."""
    seed = await db.get(Crime, crime_id)
    if seed is None:
        raise LookupError("Case not found")
    crime_ids: set[uuid.UUID] = {crime_id}
    entity_ids: set[uuid.UUID] = set()
    frontier: deque[tuple[str, uuid.UUID, int]] = deque([("crime", crime_id, 0)])
    while frontier and len(crime_ids) < _MAX_CASES:
        kind, node, level = frontier.popleft()
        if level >= 3:
            continue
        if kind == "crime":
            for e in (await db.execute(select(EntityMention.entity_id).where(EntityMention.crime_id == node))).scalars():
                if e not in entity_ids:
                    entity_ids.add(e)
                    frontier.append(("entity", e, level + 1))
        else:
            for c in (await db.execute(select(EntityMention.crime_id).where(EntityMention.entity_id == node))).scalars():
                if c not in crime_ids:
                    crime_ids.add(c)
                    frontier.append(("crime", c, level + 1))
    if seed.series_id:
        crime_ids |= set((await db.execute(select(Crime.id).where(Crime.series_id == seed.series_id))).scalars())

    basis = "linked"
    if len(crime_ids) < 3:
        # Nothing links it yet: fall back to the near-repeat neighbourhood of the same crime type.
        basis = "near-repeat"
        since = seed.occurred_at - timedelta(days=120)
        nearby = (await db.execute(
            select(Crime.id).where(
                Crime.crime_type == seed.crime_type,
                Crime.occurred_at >= since,
                func.ST_DWithin(func.Geography(Crime.geom), func.Geography(func.ST_SetSRID(
                    func.ST_MakePoint(seed.longitude, seed.latitude), 4326)), 1500),
            ).order_by(Crime.occurred_at.desc()).limit(25)
        )).scalars().all()
        crime_ids |= set(nearby)

    crimes = list((await db.execute(
        select(Crime).where(Crime.id.in_(crime_ids)).order_by(Crime.occurred_at)
    )).scalars().all())
    by_crime: dict[uuid.UUID, list[Entity]] = {c.id: [] for c in crimes}
    if entity_ids:
        rows = (await db.execute(
            select(EntityMention.crime_id, Entity)
            .join(Entity, Entity.id == EntityMention.entity_id)
            .where(EntityMention.entity_id.in_(entity_ids), EntityMention.crime_id.in_(by_crime.keys()))
        )).all()
        for cid, entity in rows:
            by_crime[cid].append(entity)
    return crimes, by_crime, basis


def _hour_profile(crimes: list[Crime]) -> np.ndarray:
    counts = np.full(24, 0.3)
    for c in crimes:
        hour = (c.occurred_at.astimezone(UTC) + timedelta(hours=5, minutes=30)).hour  # IST
        for d, w in ((-1, 0.25), (0, 1.0), (1, 0.25)):
            counts[(hour + d) % 24] += w
    return counts / counts.sum()


def _tempo(crimes: list[Crime], now: datetime) -> tuple[float, float]:
    """Hits per day, and how much faster the recent half runs than the older half."""
    if len(crimes) < 2:
        return 0.08, 1.0
    first, last = crimes[0].occurred_at, crimes[-1].occurred_at
    span = max((last - first).total_seconds() / 86400, 1.0)
    rate = (len(crimes) - 1) / span
    # A pattern that went quiet decays: halve the rate for every span length of silence.
    silence = max((now - last).total_seconds() / 86400, 0.0)
    rate *= 0.5 ** (silence / max(span, 7.0))
    mid = first + (last - first) / 2
    older = sum(1 for c in crimes if c.occurred_at < mid) or 1
    recent = len(crimes) - older
    accel = float(np.clip(recent / older, 0.5, 2.0))
    return float(np.clip(rate * accel, 0.03, 3.0)), accel


def _patrol_posts(points: np.ndarray, weights: np.ndarray, units: int) -> list[tuple[float, float]]:
    """Greedy cover: put each unit where the most remaining weight lies within its radius."""
    posts: list[tuple[float, float]] = []
    remaining = weights.copy()
    for _ in range(min(units, len(points))):
        scores = [
            sum(remaining[j] for j in range(len(points)) if _km(*points[i], *points[j]) <= _PATROL_RADIUS_KM)
            for i in range(len(points))
        ]
        best = int(np.argmax(scores))
        if scores[best] <= 0:
            break
        posts.append((float(points[best][0]), float(points[best][1])))
        for j in range(len(points)):
            if _km(*points[best], *points[j]) <= _PATROL_RADIUS_KM:
                remaining[j] = 0
    return posts


async def simulate(
    db: AsyncSession, crime_id: uuid.UUID, *, days: int = 14, runs: int = 300, patrols: int = 4,
    freeze: bool = True, seed: int = 7,
) -> dict[str, Any]:
    crimes, entities_by_crime, basis = await _cluster(db, crime_id)
    now = datetime.now(UTC)
    rng = np.random.default_rng(seed)

    points = np.array([[c.latitude, c.longitude] for c in crimes], dtype=float)
    age_days = np.array([max((now - c.occurred_at).total_seconds() / 86400, 0.0) for c in crimes])
    recency = np.exp(-age_days / max(np.ptp(age_days) if len(crimes) > 1 else 30.0, 14.0))
    recency /= recency.sum()
    hours = _hour_profile(crimes)
    rate, accel = _tempo(crimes, now)
    street = Counter(c.crime_type for c in crimes).most_common(1)[0][0] in STREET_TYPES
    if len(points) > 1:
        nn = [min(_km(*p, *q) for k, q in enumerate(points) if k != i) for i, p in enumerate(points)]
        sigma_km = float(np.clip(np.median(nn) * 0.6, 0.3, 2.5))
    else:
        sigma_km = 0.8

    # Offender agents: one per distinct identifier (who uses it is unknown, so it is the identifier
    # that acts), anchored on the cases it appears in. Patterns without identifiers get one agent.
    identifiers: dict[uuid.UUID, dict[str, Any]] = {}
    for idx, c in enumerate(crimes):
        for e in entities_by_crime.get(c.id, []):
            slot = identifiers.setdefault(e.id, {"id": str(e.id), "kind": e.kind, "label": e.label, "cases": []})
            slot["cases"].append(idx)
    # Single-case identifiers (a complainant's own number) are not part of the pattern.
    shared = [a for a in identifiers.values() if len(a["cases"]) >= 2]
    agents = sorted(shared, key=lambda a: -len(a["cases"]))[:8] or [
        {"id": "pattern", "kind": "pattern", "label": "Unattributed pattern", "cases": list(range(len(crimes)))}
    ]
    agent_share = np.array([len(a["cases"]) for a in agents], dtype=float)
    agent_share /= agent_share.sum()
    for a in agents:
        idx = a["cases"]
        a["anchor"] = [float(points[idx, 0].mean()), float(points[idx, 1].mean())]
        a["frozen"] = freeze and a["kind"] in MONEY_KINDS

    posts = _patrol_posts(points, recency, patrols) if street else []
    shift = set(np.argsort(hours)[-8:].tolist())  # units ride the eight riskiest hours

    first_base = np.full(runs, np.inf)
    first_int = np.full(runs, np.inf)
    hits_base = np.zeros(runs)
    hits_int = np.zeros(runs)
    day_hits_base = np.zeros((runs, days))
    day_hits_int = np.zeros((runs, days))
    hour_counts = np.zeros(24)
    district_counts: Counter[str] = Counter()
    agent_counts: Counter[str] = Counter()
    heat: Counter[tuple[float, float]] = Counter()
    prevented_by: Counter[str] = Counter()
    samples: list[list[dict[str, Any]]] = []

    for r in range(runs):
        events: list[dict[str, Any]] = []
        for d in range(days):
            for _ in range(rng.poisson(rate)):
                h = int(rng.choice(24, p=hours))
                t = d * 24 + h + float(rng.random())
                base = int(rng.choice(len(points), p=recency))
                ai = int(rng.choice(len(agents), p=agent_share))
                if agents[ai]["cases"] and rng.random() < 0.6:
                    base = int(rng.choice(agents[ai]["cases"]))
                ang, dist = rng.random() * 2 * math.pi, abs(rng.normal(0, sigma_km))
                lat = points[base, 0] + dist * math.sin(ang) / 111.0
                lng = points[base, 1] + dist * math.cos(ang) / (111.0 * math.cos(math.radians(points[base, 0])))

                stopped = None
                if agents[ai]["frozen"] and rng.random() < _FREEZE_BLOCK:
                    stopped = "freeze"
                elif posts and h in shift and any(_km(lat, lng, *p) <= _PATROL_RADIUS_KM for p in posts) \
                        and rng.random() < _PATROL_CATCH:
                    stopped = "patrol"

                hits_base[r] += 1
                day_hits_base[r, d] += 1
                first_base[r] = min(first_base[r], t)
                if stopped is None:
                    hits_int[r] += 1
                    day_hits_int[r, d] += 1
                    first_int[r] = min(first_int[r], t)
                else:
                    prevented_by[stopped] += 1
                hour_counts[h] += 1
                district_counts[crimes[base].district or "Unknown"] += 1
                agent_counts[agents[ai]["id"]] += 1
                heat[(round(lat, 3), round(lng, 3))] += 1
                if len(samples) < _SAMPLE_RUNS:
                    events.append({"t": round(t, 2), "lat": round(lat, 5), "lng": round(lng, 5),
                                   "agent": agents[ai]["id"], "stopped": stopped})
        if events and len(samples) < _SAMPLE_RUNS:
            samples.append(sorted(events, key=lambda e: e["t"]))

    def cumulative(first: np.ndarray) -> list[float]:
        return [round(float((first < (d + 1) * 24).mean()), 3) for d in range(days)]

    total = max(hits_base.sum(), 1)
    expected_base, expected_int = float(hits_base.mean()), float(hits_int.mean())
    finite = first_base[np.isfinite(first_base)]
    peak_hour = int(np.argmax(hours))
    top_district = district_counts.most_common(1)[0][0] if district_counts else None

    return {
        "seed_case": {"id": str(crime_id), "case_number": next((c.case_number for c in crimes if c.id == crime_id), None)},
        "basis": basis,
        "params": {"days": days, "runs": runs, "patrols": len(posts), "freeze": freeze,
                   "rate_per_day": round(rate, 3), "acceleration": round(accel, 2), "spread_km": round(sigma_km, 2),
                   "street_pattern": street},
        "cases": [
            {"id": str(c.id), "lat": c.latitude, "lng": c.longitude, "type": c.crime_type, "district": c.district,
             "occurred_at": c.occurred_at.isoformat(), "case_number": c.case_number}
            for c in crimes
        ],
        "agents": [
            {"id": a["id"], "kind": a["kind"], "label": a["label"], "anchor": a["anchor"], "frozen": a["frozen"],
             "cases": len(a["cases"]), "case_ids": [str(crimes[i].id) for i in a["cases"]], "share": round(agent_counts[a["id"]] / total, 3)}
            for a in agents
        ],
        "patrol_posts": [{"lat": p[0], "lng": p[1]} for p in posts],
        "outlook": {
            "p_hit_baseline": round(float(np.isfinite(first_base).mean()), 3),
            "p_hit_intervention": round(float(np.isfinite(first_int).mean()), 3),
            "expected_hits_baseline": round(expected_base, 2),
            "expected_hits_intervention": round(expected_int, 2),
            "prevented_pct": round(100 * (1 - expected_int / expected_base), 1) if expected_base else 0.0,
            "prevented_by": dict(prevented_by),
            "median_hours_to_next": round(float(np.median(finite)), 1) if finite.size else None,
            "peak_hour_ist": peak_hour,
            "likely_district": top_district,
        },
        "curve": {"baseline": cumulative(first_base), "intervention": cumulative(first_int)},
        "daily": {"baseline": [round(float(x), 2) for x in day_hits_base.mean(axis=0)],
                  "intervention": [round(float(x), 2) for x in day_hits_int.mean(axis=0)]},
        "hours": [round(float(x), 4) for x in hour_counts / max(hour_counts.sum(), 1)],
        "districts": [{"district": k, "share": round(v / total, 3)} for k, v in district_counts.most_common(8)],
        "heat": [{"lat": k[0], "lng": k[1], "w": v} for k, v in heat.most_common(250)],
        "samples": samples,
        "note": "Simulated futures for a linked pattern of places and times; not a prediction about any person.",
    }


async def seeds(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    """Cases worth simulating: the latest case behind each of the most-connected identifiers."""
    rows = (await db.execute(
        select(Entity).where(Entity.case_count >= 3).order_by(Entity.case_count.desc(), Entity.last_seen.desc()).limit(limit * 2)
    )).scalars().all()
    out, used = [], set()
    for e in rows:
        crime = (await db.execute(
            select(Crime).join(EntityMention, EntityMention.crime_id == Crime.id)
            .where(EntityMention.entity_id == e.id).order_by(Crime.occurred_at.desc()).limit(1)
        )).scalar_one_or_none()
        if crime is None or crime.id in used:
            continue
        used.add(crime.id)
        out.append({"crime_id": str(crime.id), "case_number": crime.case_number, "crime_type": crime.crime_type,
                    "district": crime.district, "identifier": e.label, "kind": e.kind, "cases": e.case_count})
        if len(out) >= limit:
            break
    return out
