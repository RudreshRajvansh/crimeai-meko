"""Shift-level hotspot model: panel construction, leakage safety, training and forecasting."""
import random
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.core.exceptions import MLServiceError
from app.ml.prediction.hotspot_predictor import (
    BLOCKS_PER_DAY,
    FEATURES,
    add_features,
    build_panel,
    forecast,
    probability_to_level,
    train_hotspot_model,
)

BASE = datetime(2025, 1, 1, tzinfo=UTC)


def _records(days=150, seed=3):
    rng = random.Random(seed)
    out = []
    for district, rate in (("Rohini", 5.0), ("Saket", 1.5), ("Dwarka", 0.4)):
        for day in range(days):
            for _ in range(int(rng.expovariate(1 / rate))):
                hour = rng.choice([20, 21, 22, 23, 0, 1]) if district == "Rohini" else rng.randint(0, 23)
                out.append({"district": district, "occurred_at": BASE + timedelta(days=day, hours=hour)})
    return out


def test_panel_includes_quiet_blocks():
    panel = build_panel([{"district": "A", "occurred_at": BASE}, {"district": "A", "occurred_at": BASE + timedelta(days=2)}])
    assert len(panel) == 2 * BLOCKS_PER_DAY + 1
    assert (panel["count"] == 0).sum() == len(panel) - 2


def test_features_never_see_the_target_block():
    """Changing a block's own count must not change that block's features (no target leakage)."""
    records = _records(days=30)
    panel = add_features(build_panel(records))
    row = panel[(panel["district"] == "Saket")].iloc[100]

    bumped = build_panel(records)
    mask = (bumped["district"] == "Saket") & (bumped["block_start"] == row["block_start"])
    bumped.loc[mask, "count"] += 50
    bumped_row = add_features(bumped).loc[lambda df: mask].iloc[0]
    for feature in FEATURES:
        assert bumped_row[feature] == pytest.approx(row[feature]), feature


def test_training_reports_honest_metrics():
    _model, report = train_hotspot_model(_records(), min_rows=100)
    assert report.n_test > 0 and report.n_train > report.n_test
    assert pd.Timestamp(report.train_until) < pd.Timestamp(BASE + timedelta(days=150))
    assert report.roc_auc is not None and 0.5 < report.roc_auc <= 1.0
    assert report.baseline_roc_auc is not None
    assert set(report.feature_importance) == set(FEATURES)


def test_insufficient_data_raises():
    with pytest.raises(MLServiceError):
        train_hotspot_model(_records(days=3), min_rows=10_000)


def test_forecast_covers_next_day_by_shift():
    records = _records()
    model, _ = train_hotspot_model(records, min_rows=100)
    timeline = forecast(model, records, now=BASE + timedelta(days=150, hours=1))
    assert len(timeline) == BLOCKS_PER_DAY
    assert {block["shift"] for block in timeline} == {"night", "morning", "afternoon", "evening"}
    night = next(b for b in timeline if b["shift"] == "night")
    assert night["predictions"][0]["district"] == "Rohini"
    assert all(0.0 <= p["probability"] <= 1.0 for b in timeline for p in b["predictions"])


@pytest.mark.parametrize(("p", "level"), [(0.05, "low"), (0.2, "medium"), (0.5, "high"), (0.9, "critical")])
def test_probability_levels(p, level):
    assert probability_to_level(p) == level


def test_shift_blocks_follow_local_time():
    """Regression: blocks were cut in UTC, so the 23:30 IST block was labelled 'evening'."""
    records = _records()
    model, _ = train_hotspot_model(records, min_rows=100)
    timeline = forecast(model, records, now=BASE + timedelta(days=150, hours=1))
    for block in timeline:
        start = pd.Timestamp(block["block_start"])
        assert start.utcoffset() == timedelta(hours=5, minutes=30)
        assert start.hour in (0, 6, 12, 18)
        assert block["shift"] == ("night", "morning", "afternoon", "evening")[start.hour // 6]
