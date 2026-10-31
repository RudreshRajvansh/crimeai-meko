"""Gemini brief endpoints: switched off without a key, cached per FIR, audited when text leaves."""
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.fir import FIRReport
from app.nlp import gemini

TEXT = "On 12/09/2025 the complainant's phone was snatched near Lajpat Nagar market by two men on a bike."
BRIEF = {"model": "gemini-test", "chars_sent": len(TEXT), "redactions": {}, "summary": "Phone snatching by two men."}


async def _fir(db, user) -> FIRReport:
    fir = FIRReport(fir_number="FIR/LAJ/2025/G1", raw_text=TEXT, submitted_by=user.id,
                    incident_date=datetime(2025, 9, 12, tzinfo=UTC), nlp_status="completed",
                    extracted_entities={"crime_type": "robbery"})
    db.add(fir)
    await db.commit()
    return fir


async def test_status_reports_off_without_a_key(client, monkeypatch, auth_headers_readonly):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    resp = await client.get("/api/v1/nlp/gemini", headers=auth_headers_readonly)
    assert resp.json() == {"enabled": False, "model": None}


async def test_brief_is_unavailable_without_a_key(client, db_session, police_user, monkeypatch, auth_headers_analyst):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    fir = await _fir(db_session, police_user)
    resp = await client.post(f"/api/v1/fir/{fir.id}/gemini-brief", headers=auth_headers_analyst)
    assert resp.status_code == 503


async def test_brief_is_cached_on_the_fir_and_audited_once(client, db_session, police_user, monkeypatch,
                                                           auth_headers_analyst):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    calls = []

    async def fake_brief(text, incident_date=None, **_):
        calls.append(text)
        return BRIEF

    monkeypatch.setattr(gemini, "case_brief", fake_brief)
    fir = await _fir(db_session, police_user)
    url = f"/api/v1/fir/{fir.id}/gemini-brief"

    first = await client.post(url, headers=auth_headers_analyst)
    second = await client.post(url, headers=auth_headers_analyst)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == BRIEF
    assert len(calls) == 1, "the second request is served from the FIR, not Gemini"

    await client.post(f"{url}?refresh=true", headers=auth_headers_analyst)
    assert len(calls) == 2

    stored = (await client.get(f"/api/v1/fir/{fir.id}", headers=auth_headers_analyst)).json()
    assert stored["extracted_entities"]["gemini"] == BRIEF
    assert stored["extracted_entities"]["crime_type"] == "robbery", "the rules-based reading is kept"
    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action == "fir.gemini_brief"))).scalars().all()
    assert len(audits) == 2


async def test_preview_needs_police_role(client, monkeypatch, auth_headers_analyst, auth_headers_police):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    async def fake_brief(text, incident_date=None, **_):
        return BRIEF

    monkeypatch.setattr(gemini, "case_brief", fake_brief)
    body = {"text": TEXT}
    assert (await client.post("/api/v1/nlp/gemini-brief", json=body, headers=auth_headers_analyst)).status_code == 403
    resp = await client.post("/api/v1/nlp/gemini-brief", json=body, headers=auth_headers_police)
    assert resp.status_code == 200 and resp.json()["summary"] == BRIEF["summary"]
