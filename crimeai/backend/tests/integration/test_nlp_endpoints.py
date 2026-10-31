"""Integration tests for /api/v1/nlp and /api/v1/fir endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


# Mock spaCy so integration tests run without model installed
def _make_mock_doc(entities=None):
    doc = MagicMock()
    doc.ents = []
    return doc


SAMPLE_FIR_TEXT = (
    "On 15/06/2024 at approximately 14:30 hours the complainant reported "
    "that his motorcycle was stolen from near Connaught Place market. "
    "The accused aged 25 years with fair complexion was wearing a blue shirt. "
    "A knife was found at the scene. IPC Section 379 has been invoked."
)


@pytest.fixture(autouse=True)
def mock_spacy_for_integration():
    mock_nlp = MagicMock()
    mock_nlp.return_value = _make_mock_doc()
    with patch("app.nlp.parsers.entity_extractor._get_nlp", return_value=mock_nlp):
        yield


@pytest.mark.asyncio
async def test_nlp_extract_returns_structure(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post(
        "/api/v1/nlp/extract",
        json={"text": SAMPLE_FIR_TEXT},
        headers=auth_headers_police,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "crime_type" in data
    assert "weapons" in data
    assert "locations" in data
    assert "overall_confidence" in data


@pytest.mark.asyncio
async def test_nlp_extract_uses_the_incident_date_for_the_governing_code(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    before = await client.post("/api/v1/nlp/extract", json={"text": SAMPLE_FIR_TEXT, "incident_date": "2024-06-15"},
                               headers=auth_headers_police)
    after = await client.post("/api/v1/nlp/extract", json={"text": SAMPLE_FIR_TEXT, "incident_date": "2026-10-21"},
                              headers=auth_headers_police)
    assert before.status_code == after.status_code == 200, after.text
    assert before.json()["legal"]["governing_code"] == "IPC" and not before.json()["legal"]["warnings"]
    assert after.json()["legal"]["governing_code"] == "BNS"
    assert any("IPC s.379" in w for w in after.json()["legal"]["warnings"])


@pytest.mark.asyncio
async def test_nlp_extract_detects_theft(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post(
        "/api/v1/nlp/extract",
        json={"text": SAMPLE_FIR_TEXT},
        headers=auth_headers_police,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["crime_type"] == "theft"


@pytest.mark.asyncio
async def test_nlp_extract_requires_police_role(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/nlp/extract",
        json={"text": SAMPLE_FIR_TEXT},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_nlp_extract_short_text_rejected(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post(
        "/api/v1/nlp/extract",
        json={"text": "Too short"},
        headers=auth_headers_police,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_nlp_classify_endpoint(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.post(
        "/api/v1/nlp/classify",
        json={"text": "The accused robbed the victim at knifepoint and stole his phone."},
        headers=auth_headers_police,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "crime_type" in data
    assert "confidence" in data
    assert "method" in data


@pytest.mark.asyncio
async def test_fir_submit_and_get(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    # Submit FIR (NLP task will be queued but not run in test)
    with patch("app.services.nlp_service.enqueue", return_value="test-task-id"):
        resp = await client.post(
            "/api/v1/fir/",
            json={
                "fir_number": "FIR-TEST-001",
                "raw_text": SAMPLE_FIR_TEXT,
            },
            headers=auth_headers_police,
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["fir_number"] == "FIR-TEST-001"
    assert data["nlp_status"] == "pending"
    fir_id = data["id"]

    # Retrieve it
    resp2 = await client.get(f"/api/v1/fir/{fir_id}", headers=auth_headers_police)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == fir_id


@pytest.mark.asyncio
async def test_fir_duplicate_number_rejected(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    with patch("app.services.nlp_service.enqueue", return_value="t1"):
        await client.post(
            "/api/v1/fir/",
            json={"fir_number": "FIR-DUP-001", "raw_text": SAMPLE_FIR_TEXT},
            headers=auth_headers_police,
        )
        resp = await client.post(
            "/api/v1/fir/",
            json={"fir_number": "FIR-DUP-001", "raw_text": SAMPLE_FIR_TEXT},
            headers=auth_headers_police,
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_fir_list(
    client: AsyncClient, auth_headers_police: dict
) -> None:
    resp = await client.get("/api/v1/fir/", headers=auth_headers_police)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_analyst_sees_redacted_fir_text(
    client: AsyncClient, auth_headers_police: dict, auth_headers_analyst: dict
) -> None:
    narrative = SAMPLE_FIR_TEXT + " Complainant mobile 9876543210, email complainant@example.com."
    with patch("app.services.nlp_service.enqueue", return_value="t2"):
        created = await client.post(
            "/api/v1/fir/", json={"fir_number": "FIR-PII-001", "raw_text": narrative}, headers=auth_headers_police
        )
    fir_id = created.json()["id"]
    officer_view = (await client.get(f"/api/v1/fir/{fir_id}", headers=auth_headers_police)).json()
    analyst_view = (await client.get(f"/api/v1/fir/{fir_id}", headers=auth_headers_analyst)).json()
    assert "9876543210" in officer_view["text"] and officer_view["text_redacted"] is False
    assert "9876543210" not in analyst_view["text"] and analyst_view["text_redacted"] is True


@pytest.mark.asyncio
async def test_upload_rejects_disguised_executable(client: AsyncClient, auth_headers_police: dict) -> None:
    resp = await client.post(
        "/api/v1/fir/upload",
        data={"fir_number": "FIR-UP-001"},
        files={"file": ("report.pdf", bytes([0x4D, 0x5A, 0x90, 0x00, 0x03, 0x00]), "application/pdf")},
        headers=auth_headers_police,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_legal_sections_flags_ipc_after_bns(client: AsyncClient, auth_headers_readonly: dict) -> None:
    resp = await client.post(
        "/api/v1/nlp/legal-sections",
        json={"text": "Registered u/s 379 IPC", "incident_date": "2025-02-01"},
        headers=auth_headers_readonly,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["governing_code"] == "BNS"
    assert body["mapped"][0]["bns"] == "303(2)"
    assert body["warnings"]
