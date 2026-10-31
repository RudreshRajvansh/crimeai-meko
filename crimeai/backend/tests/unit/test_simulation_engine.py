"""Unit tests for the Monte Carlo simulation engine."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from app.graph.algorithms.simulation_engine import (
    _SCENARIO_COEFFICIENTS,
    _compute_intervention_strength,
    _daily_rate_to_risk_level,
    list_scenarios,
    run_simulation,
)


def _make_crime_history(
    district: str = "TestDistrict",
    n: int = 60,
    crime_type: str = "theft",
) -> list[dict]:
    base = datetime.now(UTC) - timedelta(days=60)
    return [
        {
            "id": f"c{i}",
            "district": district,
            "crime_type": crime_type,
            "severity": 2,
            "lat": 28.63 + 0.001 * i,
            "lng": 77.22 + 0.001 * i,
            "occurred_at": (base + timedelta(hours=i * 24)).isoformat(),
        }
        for i in range(n)
    ]


class TestDailyRateToRiskLevel:
    def test_low(self):
        assert _daily_rate_to_risk_level(0.5) == "low"

    def test_medium(self):
        assert _daily_rate_to_risk_level(2.0) == "medium"

    def test_high(self):
        assert _daily_rate_to_risk_level(5.0) == "high"

    def test_critical(self):
        assert _daily_rate_to_risk_level(10.0) == "critical"


class TestComputeInterventionStrength:
    def test_patrol_30pct(self):
        strength = _compute_intervention_strength("patrol_increase", {"increase_pct": 30})
        assert strength == pytest.approx(0.30, abs=0.01)

    def test_patrol_100pct_capped_at_1(self):
        strength = _compute_intervention_strength("patrol_increase", {"increase_pct": 150})
        assert strength <= 1.0

    def test_curfew_hours_affect_strength(self):
        few_hours = _compute_intervention_strength("curfew", {"hours": [22, 23], "duration_days": 7})
        many_hours = _compute_intervention_strength("curfew", {"hours": list(range(20, 24)) + list(range(0, 6)), "duration_days": 7})
        assert many_hours > few_hours

    def test_tech_deployment_coverage(self):
        low = _compute_intervention_strength("tech_deployment", {"coverage_pct": 20})
        high = _compute_intervention_strength("tech_deployment", {"coverage_pct": 80})
        assert high > low

    def test_all_strength_in_range(self):
        for scenario in _SCENARIO_COEFFICIENTS:
            s = _compute_intervention_strength(scenario, {})
            assert 0.0 <= s <= 1.0, f"{scenario} strength out of range: {s}"


class TestRunSimulation:
    def test_basic_run_returns_result(self):
        crimes = _make_crime_history(n=60)
        result = run_simulation(
            scenario="patrol_increase",
            district="TestDistrict",
            parameters={"increase_pct": 30},
            crime_history=crimes,
            num_simulations=50,
        )
        assert result is not None
        d = result.to_dict()
        assert "simulation_id" in d
        assert "baseline" in d
        assert "projected" in d
        assert "reduction" in d

    def test_patrol_increase_reduces_crime(self):
        crimes = _make_crime_history(n=120)
        result = run_simulation(
            scenario="patrol_increase",
            district="TestDistrict",
            parameters={"increase_pct": 50},
            crime_history=crimes,
            num_simulations=100,
        )
        d = result.to_dict()
        # Median reduction should be positive
        assert d["reduction"]["p50_pct"] >= 0

    def test_curfew_reduces_crime(self):
        crimes = _make_crime_history(n=60)
        result = run_simulation(
            scenario="curfew",
            district="TestDistrict",
            parameters={"hours": [22, 23, 0, 1, 2, 3], "duration_days": 7},
            crime_history=crimes,
            num_simulations=50,
        )
        d = result.to_dict()
        assert d["reduction"]["p50_pct"] >= 0

    def test_invalid_scenario_raises(self):
        crimes = _make_crime_history(n=30)
        with pytest.raises(ValueError, match="Unknown scenario"):
            run_simulation(
                scenario="does_not_exist",
                district="TestDistrict",
                parameters={},
                crime_history=crimes,
                num_simulations=10,
            )

    def test_result_has_distribution_stats(self):
        crimes = _make_crime_history(n=60)
        result = run_simulation(
            scenario="tech_deployment",
            district="TestDistrict",
            parameters={"coverage_pct": 60},
            crime_history=crimes,
            num_simulations=50,
        )
        d = result.to_dict()
        reduction = d["reduction"]
        assert "mean_pct" in reduction
        assert "std_pct" in reduction
        assert "p5_pct" in reduction
        assert "p50_pct" in reduction
        assert "p95_pct" in reduction
        assert "confidence_interval_95" in reduction
        assert len(reduction["confidence_interval_95"]) == 2

    def test_p5_lte_p50_lte_p95(self):
        crimes = _make_crime_history(n=60)
        result = run_simulation(
            scenario="patrol_increase",
            district="TestDistrict",
            parameters={"increase_pct": 25},
            crime_history=crimes,
            num_simulations=200,
        )
        d = result.to_dict()
        r = d["reduction"]
        assert r["p5_pct"] <= r["p50_pct"] <= r["p95_pct"]

    def test_baseline_and_projected_crimes_populated(self):
        crimes = _make_crime_history(n=60)
        result = run_simulation(
            scenario="community_policing",
            district="TestDistrict",
            parameters={"program_months": 6},
            crime_history=crimes,
            num_simulations=50,
        )
        d = result.to_dict()
        assert d["baseline"]["crimes_per_day"] > 0
        assert d["projected"]["crimes_per_day"] >= 0

    def test_risk_levels_populated(self):
        crimes = _make_crime_history(n=60)
        result = run_simulation(
            scenario="patrol_increase",
            district="TestDistrict",
            parameters={"increase_pct": 30},
            crime_history=crimes,
            num_simulations=50,
        )
        d = result.to_dict()
        assert d["baseline"]["risk_level"] in ("low", "medium", "high", "critical")
        assert d["projected"]["risk_level"] in ("low", "medium", "high", "critical")

    def test_simulation_id_is_uuid(self):
        import uuid
        crimes = _make_crime_history(n=30)
        result = run_simulation(
            scenario="patrol_increase",
            district="TestDistrict",
            parameters={},
            crime_history=crimes,
            num_simulations=20,
        )
        uuid.UUID(result.simulation_id)


class TestListScenarios:
    def test_returns_list(self):
        scenarios = list_scenarios()
        assert isinstance(scenarios, list)
        assert len(scenarios) == 5

    def test_each_scenario_has_required_keys(self):
        for sc in list_scenarios():
            assert "id" in sc
            assert "name" in sc
            assert "description" in sc
            assert "parameters" in sc

    def test_all_scenario_ids_valid(self):
        ids = {sc["id"] for sc in list_scenarios()}
        assert ids == set(_SCENARIO_COEFFICIENTS.keys())


class TestPatrolOfficers:
    """Patrol strength is planned in officers, with diminishing returns per extra officer."""

    @staticmethod
    def _plan(current: int, added: int, crime_type: str = "chain_snatching") -> dict:
        result = run_simulation(
            scenario="patrol_increase",
            district="TestDistrict",
            parameters={"current_officers": current, "additional_officers": added},
            crime_history=_make_crime_history(n=120, crime_type=crime_type),
            num_simulations=50,
            lookback_days=60,
        )
        return result.to_dict()

    def test_no_extra_officers_means_no_intervention(self):
        strength = _compute_intervention_strength("patrol_increase", {"current_officers": 40, "additional_officers": 0})
        assert strength == 0.0

    def test_more_officers_reduce_more_with_diminishing_returns(self):
        curve = self._plan(40, 20)["metadata"]["response_curve"]
        reductions = [p["reduction_pct"] for p in curve]
        assert reductions == sorted(reductions) and reductions[0] == 0.0
        gains = [b - a for a, b in pairwise(reductions)]
        assert gains[0] > gains[-1] > 0

    def test_same_officers_matter_more_in_a_smaller_force(self):
        small = _compute_intervention_strength("patrol_increase", {"current_officers": 10, "additional_officers": 5})
        large = _compute_intervention_strength("patrol_increase", {"current_officers": 100, "additional_officers": 5})
        assert small > large

    def test_plan_reports_officers_and_prevented_incidents(self):
        meta = self._plan(40, 10)["metadata"]
        assert meta["officers"] == {"current": 40, "added": 10, "total": 50, "increase_pct": 25.0}
        assert meta["prevented_per_month"] > 0
        assert meta["prevented_per_officer_month"] == pytest.approx(meta["prevented_per_month"] / 10, rel=0.01)
        assert meta["response_curve"][-1]["officers_added"] >= 20

    def test_patrols_do_not_reduce_cybercrime(self):
        meta = self._plan(40, 30, crime_type="cybercrime")["metadata"]
        assert meta["prevented_per_month"] == 0.0

    def test_baseline_uses_the_lookback_window(self):
        """120 incidents over a 60-day window is 2 a day, not 4."""
        assert self._plan(40, 10)["baseline"]["crimes_per_day"] == pytest.approx(2.0)

    def test_legacy_percentage_still_accepted(self):
        assert _compute_intervention_strength("patrol_increase", {"increase_pct": 30}) == pytest.approx(0.3)

    def test_quiet_district_outcome_is_not_dominated_by_daily_noise(self):
        """About one incident a day: the spread must reflect the intervention, not a single day's 0-3 count."""
        result = run_simulation(
            scenario="patrol_increase", district="TestDistrict",
            parameters={"current_officers": 40, "additional_officers": 10},
            crime_history=_make_crime_history(n=60, crime_type="chain_snatching"),
            num_simulations=300, lookback_days=60,
        ).to_dict()
        assert result["reduction"]["p5_pct"] > -50 and result["reduction"]["p95_pct"] < 60
        low, high = result["reduction"]["confidence_interval_95"]
        assert 0 < low < result["baseline"]["crimes_per_day"] < high < 2, "CI is in crimes per day"
