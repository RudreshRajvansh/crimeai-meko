"""
Investigation intelligence end to end on YugabyteDB: documents in, contradictions and timeline out, an officer's
review stored, and an accepted finding written to Meko as approved context that a later case recalls.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.crime import Crime
from app.models.investigation import InvestigationFinding


async def _case(db, number: str, occurred: datetime) -> Crime:
    crime = Crime(crime_type="vehicle_theft", severity=2, city="Delhi", district="Saket", latitude=28.53, longitude=77.22,
                  occurred_at=occurred, reported_at=occurred + timedelta(hours=1), case_number=number,
                  description="Motorcycle DL 5S AB 1234 was stolen from the parking at about 8 PM.")
    db.add(crime)
    await db.commit()
    return crime


async def _add(client, headers, crime_id, doc_type, title, text, recorded_at):
    resp = await client.post(f"/api/v1/investigation/cases/{crime_id}/documents", headers=headers,
                             json={"doc_type": doc_type, "title": title, "text": text, "recorded_at": recorded_at.isoformat()})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_contradictions_timeline_and_review(client, db_session, auth_headers_police, auth_headers_analyst):
    occurred = datetime.now(UTC) - timedelta(days=20)
    crime = await _case(db_session, "DL-T-INV-1", occurred)
    await _add(client, auth_headers_police, crime.id, "cctv_note", "CCTV gate 3", "The motorcycle leaves the parking at 21:04.",
               occurred + timedelta(days=1))
    await _add(client, auth_headers_police, crime.id, "seizure_memo", "Seizure memo",
               "Recovered motorcycle DL 5S AB 1243. Complainant phone 9810012345 noted.", occurred + timedelta(days=12))

    view = (await client.get(f"/api/v1/investigation/cases/{crime.id}", headers=auth_headers_analyst)).json()
    subjects = sorted(f["subject"] for f in view["findings"])
    assert subjects == ["gap", "incident_time", "vehicle"]
    assert all(f["status"] == "open" for f in view["findings"])
    assert any("[PHONE]" in d["text"] for d in view["documents"]), "documents are stored redacted"
    assert [a["name"] for a in view["agents"]][:2] == ["FIR intelligence", "Evidence intelligence"]
    assert view["timeline"][0]["kind"] in ("incident", "document")

    time_finding = next(f for f in view["findings"] if f["subject"] == "incident_time")
    readonly = await client.post(f"/api/v1/investigation/cases/{crime.id}/findings/{time_finding['fingerprint']}/review",
                                 headers=auth_headers_analyst, json={"decision": "accepted"})
    assert readonly.status_code == 403, "analysts read; officers decide"
    resp = await client.post(f"/api/v1/investigation/cases/{crime.id}/findings/{time_finding['fingerprint']}/review",
                             headers=auth_headers_police, json={"decision": "needs_investigation", "note": "Ask PW-1 again"})
    assert resp.status_code == 200 and resp.json()["status"] == "needs_investigation"

    again = (await client.get(f"/api/v1/investigation/cases/{crime.id}", headers=auth_headers_analyst)).json()
    assert next(f for f in again["findings"] if f["subject"] == "incident_time")["status"] == "needs_investigation"
    stored = (await db_session.execute(select(InvestigationFinding))).scalars().all()
    assert [s.status for s in stored] == ["needs_investigation"]


async def test_accepted_finding_becomes_meko_context_for_a_later_case(client, db_session, auth_headers_police, meko):
    occurred = datetime.now(UTC) - timedelta(days=10)
    first = await _case(db_session, "DL-T-INV-2", occurred)
    await _add(client, auth_headers_police, first.id, "seizure_memo", "Seizure memo", "Recovered motorcycle DL 5S AB 1243.",
               occurred + timedelta(days=2))
    view = (await client.get(f"/api/v1/investigation/cases/{first.id}", headers=auth_headers_police)).json()
    vehicle = next(f for f in view["findings"] if f["subject"] == "vehicle")
    accepted = (await client.post(f"/api/v1/investigation/cases/{first.id}/findings/{vehicle['fingerprint']}/review",
                                  headers=auth_headers_police, json={"decision": "accepted"})).json()
    assert accepted["meko"]["status"] == "ok" and accepted["meko"]["promoted"]

    later = await _case(db_session, "DL-T-INV-3", occurred + timedelta(days=3))
    recalled = (await client.get(f"/api/v1/investigation/cases/{later.id}", headers=auth_headers_police)).json()["meko"]
    assert recalled["status"] == "ok"
    assert any("DL-T-INV-2" in item["text"] for item in recalled["items"]), "the approved finding reaches the next case"
    off = (await client.get(f"/api/v1/investigation/cases/{later.id}?meko=false", headers=auth_headers_police)).json()["meko"]
    assert off["status"] == "off" and off["items"] == []
