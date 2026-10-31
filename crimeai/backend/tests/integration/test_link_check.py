"""The scan-time "have we seen this number before?" check: read-only, cross-language, police only."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.crime import Crime
from app.models.entity import Entity, EntityMention
from app.services.entity_graph import _keyed

UPI = "quickcash.help@okaxis"


async def _ring(db) -> Entity:
    now = datetime.now(UTC)
    crimes = [
        Crime(crime_type="fraud", severity=3, city="Delhi", district=district, latitude=28.6, longitude=77.2,
              occurred_at=now - timedelta(days=days), case_number=f"DL-CHK-{i}")
        for i, (district, days) in enumerate([("Dwarka", 9), ("Rohini", 2)])
    ]
    upi = Entity(kind="upi", key=_keyed(UPI), label="qu••••••••lp@okaxis", case_count=2)
    db.add_all([*crimes, upi])
    await db.flush()
    db.add_all([EntityMention(entity_id=upi.id, crime_id=c.id) for c in crimes])
    await db.commit()
    return upi


async def test_hindi_fir_finds_the_upi_id_already_on_record(client, db_session, auth_headers_police):
    upi = await _ring(db_session)
    entities_before = (await db_session.execute(select(func.count(Entity.id)))).scalar_one()
    text = f"शिकायतकर्ता ने नौकरी के नाम पर UPI {UPI} पर 12000 रुपये भेजे। फोन 9876543210 से कॉल आया था।"

    resp = await client.post("/api/v1/graph/check", json={"text": text}, headers=auth_headers_police)

    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "hi"
    upi_match = next(m for m in body["matches"] if m["kind"] == "upi")
    assert upi_match["entity_id"] == str(upi.id)
    assert upi_match["case_count"] == 2 and upi_match["districts"] == ["Dwarka", "Rohini"]
    assert [c["case_number"] for c in upi_match["cases"]] == ["DL-CHK-1", "DL-CHK-0"]  # newest first
    phone = next(m for m in body["matches"] if m["kind"] == "phone")
    assert phone["case_count"] == 0 and phone["entity_id"] is None
    assert "9876543210" not in resp.text  # only masked labels leave the server
    assert body["known"] == 1
    # Read-only: checking a text never creates entities.
    assert (await db_session.execute(select(func.count(Entity.id)))).scalar_one() == entities_before


async def test_check_needs_police_role(client, db_session, auth_headers_analyst):
    resp = await client.post("/api/v1/graph/check", json={"text": f"Paid to UPI {UPI} for a job"},
                             headers=auth_headers_analyst)
    assert resp.status_code == 403
