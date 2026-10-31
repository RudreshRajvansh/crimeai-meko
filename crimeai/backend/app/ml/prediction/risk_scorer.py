"""
District risk index (0-100).

The index is on an absolute scale: it does not rank districts against each
other, so a quiet city does not have a "critical" district simply because some
district must be the worst. It combines

  * burden: harm-weighted crimes per day, recency weighted, saturating via
    100 * (1 - exp(-burden / scale))
  * trend: the last 7 days against the district's own 90-day baseline

Danger weights reflect harm to persons, informed by the maximum punishment
bands of the corresponding BNS offences. They are configuration, not truth,
and are reported back with every score so analysts can see why a number moved.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import pandas as pd

CRIME_DANGER_WEIGHTS: dict[str, float] = {
    "murder": 10.0,
    "kidnapping": 9.0,
    "sexual_offense": 9.0,
    "armed_robbery": 8.5,
    "robbery": 7.0,
    "domestic_violence": 6.5,
    "assault": 6.5,
    "chain_snatching": 6.0,
    "extortion": 6.0,
    "arson": 5.5,
    "burglary": 5.0,
    "drug_offense": 5.0,
    "fraud": 4.0,
    "vehicle_theft": 3.5,
    "theft": 3.5,
    "cybercrime": 3.0,
    "vandalism": 2.0,
    "trespass": 1.5,
    "traffic_violation": 1.0,
    "other": 2.0,
}
DEFAULT_DANGER_WEIGHT = 2.5

LEVEL_BANDS = ((20.0, "low"), (45.0, "medium"), (70.0, "high"))


def score_to_level(score: float) -> str:
    for upper, level in LEVEL_BANDS:
        if score < upper:
            return level
    return "critical"


def _recency_weight(days_ago: pd.Series) -> pd.Series:
    return pd.Series(1.0, index=days_ago.index).mask(days_ago <= 30, 2.0).mask(days_ago <= 7, 3.0)


def compute_district_risk_scores(
    crime_records: list[dict],
    lookback_days: int = 90,
    scale: float = 6.0,
    now: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    if not crime_records:
        return {}
    now = now or datetime.now(UTC)

    df = pd.DataFrame(crime_records)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df["district"] = df["district"].fillna("Unknown")
    df["days_ago"] = (pd.Timestamp(now) - df["occurred_at"]).dt.total_seconds() / 86400
    df = df[(df["days_ago"] >= 0) & (df["days_ago"] <= lookback_days)]
    if df.empty:
        return {}

    df["danger"] = df["crime_type"].map(CRIME_DANGER_WEIGHTS).fillna(DEFAULT_DANGER_WEIGHT)
    df["harm"] = df["danger"] * (df["severity"].clip(1, 5) / 5.0) * _recency_weight(df["days_ago"])

    results: dict[str, dict[str, Any]] = {}
    for district, group in df.groupby("district"):
        burden = float(group["harm"].sum()) / lookback_days
        recent_7d = int((group["days_ago"] <= 7).sum())
        recent_30d = int((group["days_ago"] <= 30).sum())
        baseline_weekly = len(group) / lookback_days * 7
        trend_ratio = (recent_7d / baseline_weekly) if baseline_weekly > 0 else 0.0
        score = round(min(100.0, 100.0 * (1 - math.exp(-burden / scale))), 2)
        results[str(district)] = {
            "score": score,
            "level": score_to_level(score),
            "trend": "rising" if trend_ratio >= 1.3 else "falling" if trend_ratio <= 0.7 else "stable",
            "components": {
                "total_crimes": len(group),
                "recent_7d": recent_7d,
                "recent_30d": recent_30d,
                "harm_per_day": round(burden, 4),
                "trend_ratio": round(trend_ratio, 3),
                "avg_severity": round(float(group["severity"].mean()), 2),
                "top_types": group["crime_type"].value_counts().head(3).to_dict(),
            },
            "computed_at": now.isoformat(),
        }
    return results


def score_single_crime(crime_type: str, severity: int, district_score: float, occurred_at: datetime) -> float:
    """Risk for one incident: its own harm, lifted by the risk of the area it happened in."""
    danger = CRIME_DANGER_WEIGHTS.get(crime_type, DEFAULT_DANGER_WEIGHT)
    days_ago = max((datetime.now(UTC) - occurred_at).total_seconds() / 86400, 0)
    recency = 1.0 if days_ago <= 7 else 0.8 if days_ago <= 30 else 0.6
    incident = (danger / 10.0) * (max(1, min(severity, 5)) / 5.0) * recency * 100
    return round(min(100.0, 0.7 * incident + 0.3 * district_score), 2)
