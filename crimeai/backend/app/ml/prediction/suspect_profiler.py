"""
Suspect Behavior Profiling Module
-----------------------------------
Analyses crime patterns to generate behavioral profiles of crime
activity in a given area or time window. Does NOT profile individuals —
profiles aggregate crime *patterns* to help patrol planning.

Outputs:
  - Active crime hours (temporal signature)
  - Typical MO (modus operandi) — crime type + location type combinations
  - Escalation score (severity trend over time)
  - Predicted next-crime window
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


def build_area_profile(
    crime_records: list[dict],
    district: str,
    lookback_days: int = 60,
) -> dict[str, Any]:
    """
    Build a behavioral pattern profile for a district.

    crime_records: list of dicts with keys:
        id, district, crime_type, sub_type, severity, occurred_at,
        latitude, longitude

    Returns a dict with profiling results.
    """
    df = pd.DataFrame(crime_records)
    if df.empty:
        return {"district": district, "status": "insufficient_data"}

    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df = df[df["district"] == district].copy()

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    df = df[df["occurred_at"] >= cutoff]

    if len(df) < 5:
        return {
            "district": district,
            "status": "insufficient_data",
            "total_crimes": len(df),
        }

    df["hour"] = df["occurred_at"].dt.hour
    df["day_of_week"] = df["occurred_at"].dt.day_name()
    df["week_number"] = df["occurred_at"].dt.isocalendar().week.astype(int)

    hourly_dist = df["hour"].value_counts().sort_index()
    peak_hours = hourly_dist[hourly_dist >= hourly_dist.quantile(0.75)].index.tolist()

    day_dist = df["day_of_week"].value_counts()
    most_active_day = day_dist.idxmax() if not day_dist.empty else "Unknown"

    # Time-of-day bucket summary
    time_buckets = {
        "night_22_to_5": int(((df["hour"] >= 22) | (df["hour"] <= 5)).sum()),
        "morning_6_to_11": int(((df["hour"] >= 6) & (df["hour"] <= 11)).sum()),
        "afternoon_12_to_17": int(((df["hour"] >= 12) & (df["hour"] <= 17)).sum()),
        "evening_18_to_21": int(((df["hour"] >= 18) & (df["hour"] <= 21)).sum()),
    }
    dominant_time = max(time_buckets, key=time_buckets.get)  # type: ignore[arg-type]

    type_counts = df["crime_type"].value_counts()
    dominant_crime_type = type_counts.idxmax() if not type_counts.empty else "unknown"
    crime_type_distribution = type_counts.to_dict()

    # Sub-type breakdown for dominant type
    dominant_subtypes: dict[str, int] = {}
    if "sub_type" in df.columns:
        sub = df[df["crime_type"] == dominant_crime_type]["sub_type"].dropna()
        dominant_subtypes = sub.value_counts().to_dict()

    # Weekly average severity — are crimes getting more severe?
    weekly_severity = (
        df.groupby("week_number")["severity"]
        .mean()
        .sort_index()
    )
    escalation_score = 0.0
    severity_trend = "stable"
    if len(weekly_severity) >= 2:
        # Linear regression slope
        x = np.arange(len(weekly_severity))
        y = weekly_severity.values
        slope = float(np.polyfit(x, y, 1)[0])
        escalation_score = round(slope * 10, 2)   # Scale to ≈ -10 to +10
        if slope > 0.1:
            severity_trend = "escalating"
        elif slope < -0.1:
            severity_trend = "de-escalating"

    geo_cluster: dict[str, Any] = {}
    if "latitude" in df.columns and "longitude" in df.columns:
        lat_mean = float(df["latitude"].mean())
        lng_mean = float(df["longitude"].mean())
        lat_std = float(df["latitude"].std())
        lng_std = float(df["longitude"].std())
        geo_cluster = {
            "centroid_lat": round(lat_mean, 6),
            "centroid_lng": round(lng_mean, 6),
            "spread_lat_km": round(lat_std * 111, 2),    # 1 deg lat ≈ 111 km
            "spread_lng_km": round(lng_std * 111, 2),
        }

    # Naive: based on average interval between crimes
    sorted_times = df["occurred_at"].sort_values()
    if len(sorted_times) >= 2:
        intervals = sorted_times.diff().dropna().dt.total_seconds() / 3600  # hours
        avg_interval_h = float(intervals.mean())
        last_crime_time = sorted_times.iloc[-1]
        predicted_next = last_crime_time + timedelta(hours=avg_interval_h)
        next_crime_window = {
            "avg_interval_hours": round(avg_interval_h, 1),
            "last_crime_at": last_crime_time.isoformat(),
            "predicted_next_around": predicted_next.isoformat(),
            "confidence": "low",  # naive model
        }
    else:
        next_crime_window = {"confidence": "insufficient_data"}

    from app.ml.prediction.risk_scorer import compute_district_risk_scores
    risk_data = compute_district_risk_scores(crime_records, lookback_days=lookback_days)
    district_risk = risk_data.get(district, {"score": 0, "level": "unknown"})

    profile = {
        "district": district,
        "status": "ok",
        "generated_at": datetime.now(UTC).isoformat(),
        "lookback_days": lookback_days,
        "total_crimes_analysed": len(df),
        "temporal_signature": {
            "peak_hours": sorted(peak_hours),
            "most_active_day": most_active_day,
            "time_buckets": time_buckets,
            "dominant_time_of_day": dominant_time.replace("_", " "),
        },
        "modus_operandi": {
            "dominant_crime_type": dominant_crime_type,
            "crime_type_distribution": crime_type_distribution,
            "dominant_subtypes": dominant_subtypes,
        },
        "severity_analysis": {
            "avg_severity": round(float(df["severity"].mean()), 2),
            "max_severity": int(df["severity"].max()),
            "trend": severity_trend,
            "escalation_score": escalation_score,
        },
        "geographic_hotspot": geo_cluster,
        "predicted_activity": next_crime_window,
        "risk": district_risk,
    }

    logger.info(
        "district_profile_built",
        district=district,
        n_crimes=len(df),
        dominant_type=dominant_crime_type,
    )

    return profile
