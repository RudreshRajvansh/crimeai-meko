"""
Shift-level hotspot forecasting.

Police deploy by shift, so the unit of prediction is a district x 6-hour block
(night, morning, afternoon, evening). For each block we ask: will this
district record at least `threshold` crimes in it?

Design choices that matter for validity:
  * The training panel contains every district-block, including the ones with
    zero crimes. Training only on blocks that had a crime would teach the model
    nothing about quiet periods.
  * Every feature is computed from strictly earlier blocks (shift before roll),
    so no information from the target block leaks into its own features.
  * Evaluation uses a chronological hold-out, never a random split.
  * The model is compared against a naive baseline (the district's recent
    same-shift average). If it cannot beat that, the metadata says so.
  * Blocks are cut in the force's local time zone (Asia/Kolkata by default),
    because shifts start at local hours; UTC blocks would label 23:30 IST as
    "evening".
  * Districts enter through their own historical rates, not a label encoding,
    so a newly added district is scored sensibly instead of being aliased to
    another district's ID.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from app.core.config import settings
from app.core.exceptions import MLServiceError

BLOCK_HOURS = 6
BLOCKS_PER_DAY = 24 // BLOCK_HOURS
BLOCK_LABELS = ("night", "morning", "afternoon", "evening")
_FREQ = f"{BLOCK_HOURS}h"
_WARMUP_DAYS = 7
_MIN_POSITIVE_RATE = 0.03

FEATURES = [
    "lag_prev_block",
    "lag_same_block_1d",
    "lag_same_block_7d",
    "sum_7d",
    "sum_28d",
    "same_block_mean_28d",
    "district_rate",
    "block",
    "day_of_week",
    "is_weekend",
    "month",
]


@dataclass(frozen=True, slots=True)
class TrainingReport:
    threshold: int
    n_train: int
    n_test: int
    positive_rate: float
    roc_auc: float | None
    pr_auc: float | None
    brier: float | None
    baseline_roc_auc: float | None
    beats_baseline: bool
    feature_importance: dict[str, float]
    train_until: str
    trained_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _local(ts, tz: str) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return (ts.tz_localize("UTC") if ts.tzinfo is None else ts).tz_convert(tz)


def _records_frame(records: list[dict], tz: str) -> pd.DataFrame:
    df = pd.DataFrame(records, columns=["district", "occurred_at"])
    df = df.dropna(subset=["district"])
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True).dt.tz_convert(tz)
    return df


def build_panel(
    records: list[dict], until: datetime | None = None, horizon_blocks: int = 0, tz: str | None = None
) -> pd.DataFrame:
    """District x block grid (local time) with crime counts, zeros included. Future blocks get NaN counts."""
    tz = tz or settings.APP_TIMEZONE
    df = _records_frame(records, tz)
    if df.empty:
        return pd.DataFrame(columns=["district", "block_start", "count"])

    df["block_start"] = df["occurred_at"].dt.floor(_FREQ)
    counts = df.groupby(["district", "block_start"]).size()

    start = df["block_start"].min().normalize()
    last_observed = _local(until, tz).floor(_FREQ) if until else df["block_start"].max()
    observed_range = pd.date_range(start, last_observed, freq=_FREQ)
    index = pd.MultiIndex.from_product([sorted(df["district"].unique()), observed_range], names=["district", "block_start"])
    panel = counts.reindex(index, fill_value=0).astype(float).rename("count").reset_index()

    if horizon_blocks:
        future = pd.date_range(last_observed + pd.Timedelta(hours=BLOCK_HOURS), periods=horizon_blocks, freq=_FREQ)
        future_rows = pd.MultiIndex.from_product([panel["district"].unique(), future], names=["district", "block_start"])
        panel = pd.concat([panel, pd.DataFrame(index=future_rows).reset_index().assign(count=np.nan)])

    return panel.sort_values(["district", "block_start"]).reset_index(drop=True)


def add_features(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["block"] = panel["block_start"].dt.hour // BLOCK_HOURS
    panel["day_of_week"] = panel["block_start"].dt.dayofweek
    panel["is_weekend"] = (panel["day_of_week"] >= 5).astype(int)
    panel["month"] = panel["block_start"].dt.month

    by_district = panel.groupby("district", sort=False)["count"]
    past = by_district.shift(1)
    panel["lag_prev_block"] = past
    panel["lag_same_block_1d"] = by_district.shift(BLOCKS_PER_DAY)
    panel["lag_same_block_7d"] = by_district.shift(7 * BLOCKS_PER_DAY)
    panel["sum_7d"] = past.groupby(panel["district"]).transform(
        lambda s: s.rolling(7 * BLOCKS_PER_DAY, min_periods=1).sum()
    )
    panel["sum_28d"] = past.groupby(panel["district"]).transform(
        lambda s: s.rolling(28 * BLOCKS_PER_DAY, min_periods=1).sum()
    )
    panel["district_rate"] = past.groupby(panel["district"]).transform(lambda s: s.expanding().mean())
    panel["same_block_mean_28d"] = panel.groupby(["district", "block"], sort=False)["count"].transform(
        lambda s: s.shift(1).rolling(28, min_periods=1).mean()
    )

    # Lags that fall inside the forecast horizon are unknown; use the district's long-run rate.
    for column in ("lag_prev_block", "lag_same_block_1d", "lag_same_block_7d", "same_block_mean_28d"):
        panel[column] = panel[column].fillna(panel["district_rate"])
    panel[FEATURES] = panel[FEATURES].fillna(0.0)
    return panel


def _choose_threshold(counts: pd.Series) -> int:
    return 2 if (counts >= 2).mean() >= _MIN_POSITIVE_RATE else 1


def train_hotspot_model(records: list[dict], min_rows: int = 200) -> tuple[HistGradientBoostingClassifier, TrainingReport]:
    if len(records) < min_rows:
        raise MLServiceError(
            "Insufficient data for hotspot training",
            detail={"n_records": len(records), "minimum": min_rows},
        )

    panel = add_features(build_panel(records))
    panel = panel[panel["block_start"] >= panel["block_start"].min() + pd.Timedelta(days=_WARMUP_DAYS)]
    threshold = _choose_threshold(panel["count"])
    panel["target"] = (panel["count"] >= threshold).astype(int)

    cutoff = panel["block_start"].quantile(0.8)
    train = panel[panel["block_start"] <= cutoff]
    test = panel[panel["block_start"] > cutoff]
    if train["target"].nunique() < 2:
        raise MLServiceError("Training window contains only one outcome class", detail={"threshold": threshold})

    model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, random_state=42)
    model.fit(train[FEATURES], train["target"])

    roc = pr = brier = baseline = None
    if test["target"].nunique() == 2:
        probabilities = model.predict_proba(test[FEATURES])[:, 1]
        roc = float(roc_auc_score(test["target"], probabilities))
        pr = float(average_precision_score(test["target"], probabilities))
        brier = float(brier_score_loss(test["target"], probabilities))
        baseline = float(roc_auc_score(test["target"], test["same_block_mean_28d"]))

    importance = _permutation_free_importance(model, train)
    report = TrainingReport(
        threshold=threshold,
        n_train=len(train),
        n_test=len(test),
        positive_rate=round(float(panel["target"].mean()), 4),
        roc_auc=roc,
        pr_auc=pr,
        brier=brier,
        baseline_roc_auc=baseline,
        beats_baseline=bool(roc is not None and baseline is not None and roc > baseline),
        feature_importance=importance,
        train_until=cutoff.isoformat(),
        trained_at=datetime.now(UTC).isoformat(),
    )
    # Refit on the full history so the deployed model sees the most recent weeks.
    model.fit(panel[FEATURES], panel["target"])
    return model, report


def _permutation_free_importance(model: HistGradientBoostingClassifier, frame: pd.DataFrame) -> dict[str, float]:
    """Cheap sensitivity score: mean absolute change in probability when one feature is set to its median."""
    sample = frame[FEATURES].tail(min(len(frame), 2000))
    base = model.predict_proba(sample)[:, 1]
    scores = {}
    for feature in FEATURES:
        perturbed = sample.copy()
        perturbed[feature] = sample[feature].median()
        scores[feature] = float(np.abs(model.predict_proba(perturbed)[:, 1] - base).mean())
    total = sum(scores.values()) or 1.0
    return {k: round(v / total, 4) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])}


def forecast(
    model: HistGradientBoostingClassifier,
    records: list[dict],
    now: datetime | None = None,
    horizon_blocks: int = BLOCKS_PER_DAY,
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    last_complete = _local(now, settings.APP_TIMEZONE).floor(_FREQ) - pd.Timedelta(hours=BLOCK_HOURS)
    panel = add_features(build_panel(records, until=last_complete.to_pydatetime(), horizon_blocks=horizon_blocks))
    future = panel[panel["count"].isna()].copy()
    if future.empty:
        return []
    future["probability"] = model.predict_proba(future[FEATURES])[:, 1]

    timeline = []
    for block_start, rows in future.groupby("block_start"):
        predictions = [
            {
                "district": row.district,
                "probability": round(float(row.probability), 4),
                "risk_level": probability_to_level(float(row.probability)),
                "expected_baseline": round(float(row.same_block_mean_28d), 3),
            }
            for row in rows.sort_values("probability", ascending=False).itertuples()
        ]
        timeline.append({
            "block_start": block_start.isoformat(),
            "block_end": (block_start + pd.Timedelta(hours=BLOCK_HOURS)).isoformat(),
            "shift": BLOCK_LABELS[block_start.hour // BLOCK_HOURS],
            "predictions": predictions,
        })
    return timeline


def probability_to_level(probability: float) -> str:
    if probability < 0.15:
        return "low"
    if probability < 0.35:
        return "medium"
    if probability < 0.6:
        return "high"
    return "critical"


def lookback_start(days: int = 180) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)
