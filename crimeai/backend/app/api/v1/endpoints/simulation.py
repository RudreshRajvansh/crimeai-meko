"""What-if simulation of policing interventions (Monte Carlo)."""
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Analyst
from app.core.exceptions import ValidationError
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.graph_service import GraphService

router = APIRouter()

_VALID_SCENARIOS = {
    "patrol_increase",
    "resource_reallocation",
    "curfew",
    "tech_deployment",
    "community_policing",
}


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> GraphService:
    return GraphService(db=db, redis=redis)


Scenario = Literal["patrol_increase", "resource_reallocation", "curfew", "tech_deployment", "community_policing"]


class SimulationRequest(BaseModel):
    scenario: Scenario = Field(
        ...,
        description=(
            "patrol_increase | resource_reallocation | "
            "curfew | tech_deployment | community_policing"
        ),
    )
    district: str = Field(..., min_length=2, max_length=100)
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Scenario-specific params. Examples:\n"
            "- patrol_increase: {'current_officers': 40, 'additional_officers': 10}\n"
            "- curfew: {'hours': [22,23,0,1,2,3], 'duration_days': 7}\n"
            "- tech_deployment: {'coverage_pct': 60}\n"
            "- community_policing: {'program_months': 3}"
        ),
    )
    num_simulations: int = Field(
        default=200,
        ge=10,
        le=1000,
        description="Monte Carlo trial count. More = more accurate, slower.",
    )


@router.get(
    "/scenarios",
    summary="List available simulation scenarios with parameters",
)
async def list_scenarios(
    user: Analyst,
    service: Annotated[GraphService, Depends(_get_service)],
) -> list[dict]:
    """
    Returns all supported simulation scenarios with their parameter schemas.
    Use this to build the UI scenario picker.
    """
    return await service.get_scenario_list()


@router.post(
    "/run",
    summary="Run Monte Carlo crime intervention simulation (Analyst+)",
)
async def run_simulation(
    body: SimulationRequest,
    user: Analyst,
    service: Annotated[GraphService, Depends(_get_service)],
) -> dict:
    """
    Runs a Monte Carlo simulation to predict the impact of a crime-reduction
    intervention on a specific district.

    The engine:
    1. Estimates baseline crime rate per day from the last 60 days of data
    2. Applies evidence-based crime-reduction coefficients per crime type
    3. Runs N Monte Carlo trials with Gaussian noise on intervention effectiveness
    4. Returns full distribution statistics (mean, std, P5/P50/P95, 95% CI)

    **Interpretation guide:**
    - `reduction.p5_pct`: pessimistic estimate (only 5% of simulations do better)
    - `reduction.p50_pct`: median expected reduction
    - `reduction.p95_pct`: optimistic estimate (only 5% of simulations do better)
    - `confidence_interval_95`: 95% CI on daily crime count after intervention

    **Limitations:**
    - Based on statistical patterns, not causal models
    - Does not account for crime displacement to neighbouring districts
    - Coefficients are generalised; local calibration improves accuracy
    """
    return await service.run_what_if(
        scenario=body.scenario,
        district=body.district,
        parameters=body.parameters,
        num_simulations=body.num_simulations,
    )


@router.post(
    "/compare",
    summary="Compare multiple scenarios side-by-side (Analyst+)",
)
async def compare_scenarios(
    user: Analyst,
    service: Annotated[GraphService, Depends(_get_service)],
    district: str = Query(..., min_length=2),
    scenarios: str = Query(
        ...,
        description="Comma-separated scenario IDs, e.g. patrol_increase,curfew",
    ),
    num_simulations: int = Query(default=100, ge=10, le=500),
) -> dict:
    """
    Runs multiple scenarios for the same district and returns a
    side-by-side comparison. Useful for budget / resource planning.

    Returns scenarios ranked by expected crime reduction (median).
    """
    scenario_list = [s.strip() for s in scenarios.split(",") if s.strip() in _VALID_SCENARIOS]
    if not scenario_list:
        raise ValidationError("No valid scenarios provided", detail={"valid": sorted(_VALID_SCENARIOS)})

    results = []
    for scenario in scenario_list:
        result = await service.run_what_if(
            scenario=scenario,
            district=district,
            parameters={},   # Use defaults for comparison
            num_simulations=num_simulations,
        )
        results.append({
            "scenario": scenario,
            "reduction_p50_pct": result.get("reduction", {}).get("p50_pct", 0),
            "reduction_p5_pct": result.get("reduction", {}).get("p5_pct", 0),
            "reduction_p95_pct": result.get("reduction", {}).get("p95_pct", 0),
            "projected_crimes_per_day": result.get("projected", {}).get("crimes_per_day", 0),
            "baseline_crimes_per_day": result.get("baseline", {}).get("crimes_per_day", 0),
            "full_result": result,
        })

    # Rank by median reduction
    results.sort(key=lambda x: x["reduction_p50_pct"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return {
        "district": district,
        "comparison": results,
        "best_scenario": results[0]["scenario"] if results else None,
        "generated_at": datetime.now(UTC).isoformat(),
    }
