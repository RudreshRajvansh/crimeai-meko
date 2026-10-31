"""Integration tests for /api/v1/simulation and /api/v1/patrol endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_scenarios(
    client: AsyncClient, auth_headers_admin: dict
) -> None:
    resp = await client.get(
        "/api/v1/simulation/scenarios",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 5
    ids = {s["id"] for s in data}
    assert "patrol_increase" in ids
    assert "curfew" in ids


@pytest.mark.asyncio
async def test_run_simulation_requires_analyst(
    client: AsyncClient, auth_headers_readonly: dict
) -> None:
    resp = await client.post(
        "/api/v1/simulation/run",
        json={
            "scenario": "patrol_increase",
            "district": "Connaught Place",
            "parameters": {"increase_pct": 30},
            "num_simulations": 20,
        },
        headers=auth_headers_readonly,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_run_simulation_invalid_scenario(
    client: AsyncClient, auth_headers_admin: dict
) -> None:
    resp = await client.post(
        "/api/v1/simulation/run",
        json={
            "scenario": "invalid_scenario",
            "district": "Connaught Place",
            "parameters": {},
            "num_simulations": 20,
        },
        headers=auth_headers_admin,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_scenarios(
    client: AsyncClient, auth_headers_admin: dict
) -> None:
    # No crime data in test DB → should return insufficient_data
    resp = await client.post(
        "/api/v1/simulation/compare",
        params={
            "district": "TestDistrict",
            "scenarios": "patrol_increase,curfew",
            "num_simulations": 20,
        },
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "district" in data
    assert "comparison" in data


@pytest.mark.asyncio
async def test_patrol_optimize_requires_police(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/patrol/optimize",
        json={
            "start_lat": 28.63,
            "start_lng": 77.22,
            "district": "Connaught Place",
            "strategy": "shortest",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patrol_optimize_returns_route(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post(
        "/api/v1/patrol/optimize",
        json={
            "start_lat": 28.63,
            "start_lng": 77.22,
            "district": "Connaught Place",
            "strategy": "shortest",
            "num_checkpoints": 3,
        },
        headers=auth_headers_police,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "route_id" in data
    assert "checkpoints" in data
    assert "total_distance_km" in data
    assert "strategy" in data
    assert data["strategy"] == "shortest"


@pytest.mark.asyncio
async def test_patrol_invalid_strategy(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post(
        "/api/v1/patrol/optimize",
        json={
            "start_lat": 28.63,
            "start_lng": 77.22,
            "district": "Test",
            "strategy": "invalid",
        },
        headers=auth_headers_police,
    )
    assert resp.status_code == 422
