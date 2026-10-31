"""
Meko end to end against YugabyteDB, with an in-memory stand-in for Meko's MCP server (no network in CI).

The story: Gurugram and Noida have posted sightings to the grid. A Delhi FIR shares a caller phone and a UPI ID
with them, plus a bank customer-care number that also appears in two unrelated KYC cases. The officer excludes
the customer-care number and confirms the series; both are promoted. A later FIR with a new phone and UPI ID is
then matched to the series by method, and the excluded number is ignored, here and in local link alerts.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.meko import contract
from app.meko.models import MekoCall, MekoExclusion
from app.models.crime import Crime
from app.services import entity_graph

DEMO_1 = ("Shikayatkarta ko 90000 11223 se call aaya. Caller ne bola ki uska parcel customs mein ruka hai aur Rs 4,999 "
          "customs fee UPI ID parcelfee.clear@okdemo pe bhejni hogi. Usne GPay se payment kiya, phir bank ki WhatsApp "
          "customer care 90000 55555 pe account freeze karwaya.")
DEMO_2 = ("Complainant received a call from 90000 22334 claiming a FedEx parcel was stuck at customs and paid Rs 5,999 "
          "to UPI ID customs.desk@okdemo, then messaged the bank's WhatsApp customer care 90000 55555.")
PARTNERS = [
    ("GGM:GGM-2026-0412", "fraud", "Complainant got a call from 90000 11223, parcel held at customs, paid UPI parcelfee.clear@okdemo"),
    ("NOI:NOI-2026-0377", "fraud", "कॉल 90000 44556 से, पार्सल कस्टम में रुका, UPI parcelfee.clear@okdemo पर भुगतान"),
    ("GGM:GGM-2026-0431", "cybercrime", "KYC update, OTP shared with 90000 77889, then bank customer care 90000 55555"),
    ("NOI:NOI-2026-0391", "cybercrime", "KYC block SMS, OTP to 90000 77889, card blocked via customer care 90000 55555"),
]


@pytest.fixture
async def partners(meko):
    """Gurugram and Noida have already posted their sightings to the grid."""
    for ref, crime_type, text in PARTNERS:
        tokens = [i.token for i in contract.grid_identifiers(text)]
        meko.add("dp-grid", contract.sighting_memory(ref, None, "2026-10-20", crime_type, contract.mo_tags(text), tokens))
    return meko


def _token(text: str, label_digits: str) -> str:
    return next(i.token for i in contract.grid_identifiers(text) if label_digits in i.label)


async def test_meko_off_returns_nothing_shared(client, auth_headers_police, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MEKO_API_KEY", "")
    resp = await client.post("/api/v1/meko/recall", json={"text": DEMO_1}, headers=auth_headers_police)
    assert resp.status_code == 200
    assert resp.json()["status"] == "off" and resp.json()["calls"] == []


async def test_recall_decide_and_carry_forward(client, auth_headers_police, db_session, partners):
    meko = partners
    first = (await client.post("/api/v1/meko/recall", json={"text": DEMO_1}, headers=auth_headers_police)).json()
    assert first["status"] == "ok"
    linked = {link["ref"] for link in first["analysis"]["links"]}
    assert {"GGM:GGM-2026-0412", "NOI:NOI-2026-0377"} <= linked
    assert {"GGM:GGM-2026-0431", "NOI:NOI-2026-0391"} <= linked, "customer-care number links until excluded"
    assert all("90000" not in json.dumps(args) for _, args in meko.calls), "raw identifiers never reach Meko"
    assert (await db_session.execute(MekoCall.__table__.select())).first() is not None, "calls are logged in YugabyteDB"

    care = _token(DEMO_1, "555")
    excl = await client.post("/api/v1/meko/decisions/exclusion",
                             json={"token": care, "reason": "public customer care"}, headers=auth_headers_police)
    assert excl.status_code == 200 and excl.json()["promote"]["ok"]
    series = await client.post("/api/v1/meko/decisions/series", json={
        "own_ref": "DLP:FIR/101/2026", "refs": ["GGM:GGM-2026-0412", "NOI:NOI-2026-0377"],
        "tokens": [_token(DEMO_1, "223"), next(i.token for i in contract.grid_identifiers(DEMO_1) if i.kind == "upi")],
        "mo_tags": ["courier-customs"], "lead": "Gurugram Cyber PS", "note": "Ring rotates SIMs weekly",
    }, headers=auth_headers_police)
    assert series.status_code == 200 and series.json()["series_id"] == "SR-DLP-01" and series.json()["promote"]["ok"]

    later = (await client.post("/api/v1/meko/recall", json={"text": DEMO_2}, headers=auth_headers_police)).json()
    assert later["analysis"]["series"][0]["series_id"] == "SR-DLP-01"
    assert later["analysis"]["series"][0]["note"] == "Ring rotates SIMs weekly"
    assert [x["token"] for x in later["analysis"]["excluded"]] == [care]
    assert not {"GGM:GGM-2026-0431", "NOI:NOI-2026-0391"} & {link["ref"] for link in later["analysis"]["links"]}


async def test_link_alerts_skip_excluded_identifiers(db_session, meko):
    now = datetime.now(UTC)
    crimes = [Crime(crime_type="fraud", severity=2, city="Delhi", district=d, latitude=28.6, longitude=77.2,
                    occurred_at=now - timedelta(days=i), case_number=f"DL-MK-{i}", description="x")
              for i, d in enumerate(("Saket", "Dwarka"))]
    db_session.add_all(crimes)
    await db_session.flush()
    text = "Victim messaged bank customer care 90000 55555 to block the card."
    linked = [e for c in crimes for e in await entity_graph.link_crime(db_session, c.id, text)]
    assert len(await entity_graph.link_alerts(db_session, linked)) == 1, "without an exclusion the shared number alerts"
    token = _token(text, "555")
    db_session.add(MekoExclusion(token=token, memory_id="m1", text=contract.exclusion_memory(token, "public", "o", "d")))
    await db_session.flush()
    crimes.append(Crime(crime_type="fraud", severity=2, city="Delhi", district="Rohini", latitude=28.7, longitude=77.1,
                        occurred_at=now, case_number="DL-MK-9", description="x"))
    db_session.add(crimes[-1])
    await db_session.flush()
    again = await entity_graph.link_crime(db_session, crimes[-1].id, text)
    assert await entity_graph.link_alerts(db_session, again) == [], "a promoted exclusion silences the alert"
    await db_session.rollback()
