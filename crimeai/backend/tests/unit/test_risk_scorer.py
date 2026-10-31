"""Absolute district risk index."""
from datetime import UTC, datetime, timedelta

import pytest

from app.ml.prediction.risk_scorer import (
    CRIME_DANGER_WEIGHTS,
    compute_district_risk_scores,
    score_single_crime,
    score_to_level,
)
from app.schemas.crime import VALID_CRIME_TYPES

NOW = datetime(2025, 6, 1, tzinfo=UTC)


def _crimes(district, n, crime_type="theft", severity=2, days_ago=3):
    return [
        {"district": district, "crime_type": crime_type, "severity": severity, "occurred_at": NOW - timedelta(days=days_ago)}
        for _ in range(n)
    ]


def test_empty():
    assert compute_district_risk_scores([], now=NOW) == {}


def test_quiet_city_has_no_critical_district():
    """Regression: the old index scaled to the worst district, which was always 100/critical."""
    scores = compute_district_risk_scores(_crimes("A", 3) + _crimes("B", 1), now=NOW)
    assert all(s["level"] == "low" for s in scores.values())


def test_more_harm_scores_higher():
    scores = compute_district_risk_scores(_crimes("A", 40) + _crimes("B", 5), now=NOW)
    assert scores["A"]["score"] > scores["B"]["score"]


def test_violent_crime_weighs_more():
    scores = compute_district_risk_scores(
        _crimes("A", 10, "murder", 5) + _crimes("B", 10, "vandalism", 5), now=NOW
    )
    assert scores["A"]["score"] > scores["B"]["score"]


def test_recent_activity_weighs_more_and_shows_rising_trend():
    scores = compute_district_risk_scores(_crimes("A", 20, days_ago=2) + _crimes("B", 20, days_ago=60), now=NOW)
    assert scores["A"]["score"] > scores["B"]["score"]
    assert scores["A"]["trend"] == "rising" and scores["B"]["trend"] == "falling"


def test_score_bounded():
    scores = compute_district_risk_scores(_crimes("A", 5000, "murder", 5, days_ago=1), now=NOW)
    assert scores["A"]["score"] <= 100 and scores["A"]["level"] == "critical"


def test_every_valid_crime_type_has_a_weight():
    assert set(CRIME_DANGER_WEIGHTS) >= VALID_CRIME_TYPES


@pytest.mark.parametrize(("score", "level"), [(10, "low"), (30, "medium"), (60, "high"), (85, "critical")])
def test_levels(score, level):
    assert score_to_level(score) == level


def test_single_crime_score():
    murder = score_single_crime("murder", 5, 40.0, datetime.now(UTC))
    vandalism = score_single_crime("vandalism", 1, 40.0, datetime.now(UTC))
    assert 0 <= vandalism < murder <= 100
