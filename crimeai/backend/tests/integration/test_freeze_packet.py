"""One freeze/lien request for a mule UPI ID that links several complaints."""
from datetime import UTC, datetime, timedelta

from app.models.crime import Crime
from app.models.entity import Entity, EntityMention
from app.services.entity_graph import _keyed

UPI = "quickcash.help@okaxis"


async def _mule_ring(db) -> Entity:
    now = datetime.now(UTC)
    crimes = [
        Crime(crime_type="fraud", severity=3, city="Delhi", district=district, latitude=28.6, longitude=77.2,
              occurred_at=now - timedelta(days=days), case_number=f"DL-FRAUD-{i}",
              description=f"Victim paid Rs {amount} to UPI {UPI} for a fake job offer.")
        for i, (district, days, amount) in enumerate([("Dwarka", 9, "45,000"), ("Rohini", 2, "1,20,000")])
    ]
    upi = Entity(kind="upi", key=_keyed(UPI), label="qu••••••••lp@okaxis", case_count=2)
    plate = Entity(kind="vehicle", key="DL3SCK4471", label="DL3SCK4471", case_count=2)
    db.add_all([*crimes, upi, plate])
    await db.flush()
    db.add_all([EntityMention(entity_id=e.id, crime_id=c.id) for c in crimes for e in (upi, plate)])
    await db.commit()
    return upi, plate


async def test_packet_cites_every_complaint_and_recovers_the_identifier(client, db_session, auth_headers_police):
    upi, _ = await _mule_ring(db_session)

    resp = await client.get(f"/api/v1/graph/entities/{upi.id}/freeze-packet", headers=auth_headers_police)

    assert resp.status_code == 200
    packet = resp.json()
    assert packet["entity"]["identifier"] == UPI
    assert [c["case_number"] for c in packet["complaints"]] == ["DL-FRAUD-0", "DL-FRAUD-1"]
    assert packet["totals"]["amount"] == 165000 and packet["totals"]["districts"] == ["Dwarka", "Rohini"]
    assert UPI in packet["draft"] and "Rs 1,65,000" not in packet["draft"]  # Indian grouping is not assumed
    assert "Rs 165,000" in packet["draft"]


async def test_packet_needs_police_role(client, db_session, auth_headers_analyst):
    upi, _ = await _mule_ring(db_session)
    resp = await client.get(f"/api/v1/graph/entities/{upi.id}/freeze-packet", headers=auth_headers_analyst)
    assert resp.status_code == 403


async def test_vehicles_cannot_be_frozen(client, db_session, auth_headers_police):
    _, plate = await _mule_ring(db_session)
    resp = await client.get(f"/api/v1/graph/entities/{plate.id}/freeze-packet", headers=auth_headers_police)
    assert resp.status_code == 422
