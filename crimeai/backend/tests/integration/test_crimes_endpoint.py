"""Integration tests for /api/v1/crimes endpoints."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

CRIME_PAYLOAD = {
    "crime_type": "theft",
    "sub_type": "bike theft",
    "description": "Bicycle stolen from outside market",
    "severity": 2,
    "latitude": 28.6315,
    "longitude": 77.2167,
    "location_name": "Connaught Place Market",
    "address": "Block A, Connaught Place",
    "district": "Connaught Place",
    "city": "Delhi",
    "occurred_at": "2024-06-15T14:30:00Z",
    "status": "reported",
}

@pytest.mark.asyncio
async def test_create_crime_as_police(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post("/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["crime_type"] == "theft"
    assert data["city"] == "Delhi"
    assert "id" in data
    assert "case_number" in data


@pytest.mark.asyncio
async def test_create_crime_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/crimes/", json=CRIME_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_crime(client: AsyncClient, auth_headers_police: dict) -> None:
    create = await client.post(
        "/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police
    )
    crime_id = create.json()["id"]

    resp = await client.get(f"/api/v1/crimes/{crime_id}", headers=auth_headers_police)
    assert resp.status_code == 200
    assert resp.json()["id"] == crime_id


@pytest.mark.asyncio
async def test_get_crime_not_found(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/crimes/{fake_id}", headers=auth_headers_police)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_crimes(client: AsyncClient, auth_headers_police: dict) -> None:
    # Create two crimes
    for _ in range(2):
        await client.post(
            "/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police
        )
    resp = await client.get("/api/v1/crimes/", headers=auth_headers_police)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_crimes_filter_by_type(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    await client.post("/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police)
    resp = await client.get(
        "/api/v1/crimes/",
        params={"crime_type": "theft"},
        headers=auth_headers_police,
    )
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["crime_type"] == "theft"


@pytest.mark.asyncio
async def test_update_crime(client: AsyncClient, auth_headers_police: dict) -> None:
    create = await client.post(
        "/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police
    )
    crime_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/crimes/{crime_id}",
        json={"status": "under_investigation", "severity": 3},
        headers=auth_headers_police,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "under_investigation"
    assert resp.json()["severity"] == 3


@pytest.mark.asyncio
async def test_delete_crime_requires_admin(
    client: AsyncClient,
    auth_headers_police: dict,
    auth_headers_admin: dict,
) -> None:
    create = await client.post(
        "/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police
    )
    crime_id = create.json()["id"]

    # Police cannot delete
    resp = await client.delete(
        f"/api/v1/crimes/{crime_id}", headers=auth_headers_police
    )
    assert resp.status_code == 403

    # Admin can delete
    resp = await client.delete(
        f"/api/v1/crimes/{crime_id}", headers=auth_headers_admin
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_duplicate_case_number(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    payload = {**CRIME_PAYLOAD, "case_number": "UNIQUE-001"}
    resp1 = await client.post(
        "/api/v1/crimes/", json=payload, headers=auth_headers_police
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/crimes/", json=payload, headers=auth_headers_police
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_stats_endpoint(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    await client.post("/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police)
    resp = await client.get("/api/v1/crimes/stats", headers=auth_headers_police)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_crimes" in data
    assert "by_type" in data
    assert "by_district" in data


@pytest.mark.asyncio
async def test_future_occurred_at_rejected(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    payload = {**CRIME_PAYLOAD, "occurred_at": "2099-01-01T00:00:00Z"}
    resp = await client.post(
        "/api/v1/crimes/", json=payload, headers=auth_headers_police
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_geojson_export_requires_analyst(
    client: AsyncClient,
    auth_headers_readonly: dict,
    auth_headers_admin: dict,
) -> None:
    # Police cannot export (role is analyst minimum)
    resp = await client.get(
        "/api/v1/crimes/export/geojson", headers=auth_headers_readonly
    )
    assert resp.status_code == 403

    # Admin can (admin > analyst in hierarchy)
    resp = await client.get(
        "/api/v1/crimes/export/geojson", headers=auth_headers_admin
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data


@pytest.mark.asyncio
async def test_readonly_sees_aggregates_not_records(client: AsyncClient, auth_headers_readonly: dict) -> None:
    assert (await client.get("/api/v1/crimes/stats", headers=auth_headers_readonly)).status_code == 200
    assert (await client.get("/api/v1/crimes/", headers=auth_headers_readonly)).status_code == 403


@pytest.mark.asyncio
async def test_partial_coordinate_update_moves_geometry(client: AsyncClient, auth_headers_police: dict) -> None:
    """Regression: updating only latitude used to leave the PostGIS point at the old location."""
    created = (await client.post("/api/v1/crimes/", json=CRIME_PAYLOAD, headers=auth_headers_police)).json()
    resp = await client.patch(
        f"/api/v1/crimes/{created['id']}",
        json={"latitude": 28.70, "longitude": CRIME_PAYLOAD["longitude"]},
        headers=auth_headers_police,
    )
    assert resp.status_code == 200
    near_new = await client.get(
        "/api/v1/crimes/nearby",
        params={"latitude": 28.70, "longitude": CRIME_PAYLOAD["longitude"], "radius_km": 0.5},
        headers=auth_headers_police,
    )
    assert [c["id"] for c in near_new.json()] == [created["id"]]


@pytest.mark.asyncio
async def test_unknown_crime_type_rejected(client: AsyncClient, auth_headers_police: dict) -> None:
    resp = await client.post(
        "/api/v1/crimes/", json={**CRIME_PAYLOAD, "crime_type": "jaywalking"}, headers=auth_headers_police
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_export_is_audited(client: AsyncClient, auth_headers_admin: dict, db_session) -> None:
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    await client.get("/api/v1/crimes/export/geojson", headers=auth_headers_admin)
    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "crimes.export" in actions


@pytest.mark.asyncio
async def test_audit_log_is_append_only(db_session) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    await db_session.execute(text(
        "INSERT INTO audit_logs (action, resource_type, method, path) VALUES ('t', 't', 'GET', '/')"
    ))
    await db_session.commit()
    with pytest.raises(DBAPIError):
        await db_session.execute(text("DELETE FROM audit_logs"))
    await db_session.rollback()
