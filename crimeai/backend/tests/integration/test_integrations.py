"""CCTNS and NCRP imports, e-Sakshya links and the BNSS s.105 check, CCTNS write-back."""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.crime import Crime
from app.models.entity import Entity

# Modelled on frontend/public/samples/cctns_fir_export.json (the demo sample).
CCTNS_RECORDS = [
    {
        "fir_number": "0412/2026",
        "police_station": "Hauz Khas",
        "district": "South",
        "city": "Delhi",
        "occurred_at": "2026-09-28T21:40:00+05:30",
        "registered_at": "2026-09-29T09:10:00+05:30",
        "acts_sections": "BNS 309(4), 3(5)",
        "place_of_occurrence": "Outer Ring Road near IIT flyover",
        "latitude": 28.5494,
        "longitude": 77.189,
        "brief_facts": "Complainant states two men on a black Pulsar without number plate snatched her bag near the flyover and fled towards Munirka. Her phone and Rs 6,000 cash were in the bag. Accused Vikas was arrested on 30.09.2026 and the bag was recovered at his instance.",
        "accused_arrested_at": "2026-09-30T18:00:00+05:30",
        "first_remanded_at": "2026-10-01T11:30:00+05:30"
    },
    {
        "fir_number": "0413/2026",
        "police_station": "Saket",
        "district": "South",
        "city": "Delhi",
        "occurred_at": "2026-09-30T13:15:00+05:30",
        "acts_sections": "BNS 318(4), 61(2)",
        "brief_facts": "Complainant received a call offering a work-from-home job and paid Rs 45,000 as registration fee to UPI ID quickcash.help@okaxis and to A/c No. 50100234567891. The caller then stopped responding."
    },
    {
        "fir_number": "0414/2026",
        "police_station": "Malviya Nagar",
        "district": "South",
        "city": "Delhi",
        "occurred_at": "2026-10-02T23:05:00+05:30",
        "acts_sections": "IPC 302",
        "brief_facts": "Missing brief facts are rejected; this row demonstrates per-row error reporting.",
        "latitude": "not-a-number"
    }
]
NCRP_CSV = (
    "acknowledgement_no,complaint_date,district,category,amount,suspect_upi,suspect_phone,suspect_account,"
    "latitude,longitude\n"
    "1001,2026-10-03T10:00:00+05:30,South,Online job fraud,12000,quickcash.help@okaxis,,,28.52,77.21\n"
    "1002,2026-10-04T10:00:00+05:30,Dwarka,Investment fraud,250000,,,50100234567891,28.59,77.04\n"
    "1003,2026-10-05T10:00:00+05:30,Rohini,UPI fraud,8500,quickcash.help@okaxis,,50100234567891,28.73,77.11\n"
)


async def test_connectors_listed_with_guardrails(client, auth_headers_analyst):
    connectors = {c["id"]: c for c in (await client.get("/api/v1/integrations/", headers=auth_headers_analyst)).json()}
    assert connectors["cctns"]["status"] == "file" and connectors["ncrp"]["status"] == "file"
    assert connectors["nafis"]["status"] == "excluded" and "biometric" in connectors["nafis"]["guardrail"].lower()


async def test_ncrp_import_links_mule_identifiers_and_is_idempotent(client, db_session, auth_headers_police):
    files = {"file": ("ncrp.csv", NCRP_CSV.encode(), "text/csv")}
    first = (await client.post("/api/v1/integrations/ncrp/import", headers=auth_headers_police, files=files)).json()
    assert first["created"] == 3 and first["error_count"] == 0 and first["link_alerts"] >= 1

    upi = (await db_session.execute(select(Entity).where(Entity.kind == "upi"))).scalar_one()
    account = (await db_session.execute(select(Entity).where(Entity.kind == "account"))).scalar_one()
    assert upi.case_count == 2 and account.case_count == 2

    again = (await client.post("/api/v1/integrations/ncrp/import", headers=auth_headers_police, files=files)).json()
    assert again["created"] == 0 and again["skipped"] == 3


async def test_ncrp_import_needs_police_role(client, auth_headers_analyst):
    files = {"file": ("ncrp.csv", NCRP_CSV.encode(), "text/csv")}
    assert (await client.post("/api/v1/integrations/ncrp/import", headers=auth_headers_analyst, files=files)).status_code == 403


async def test_cctns_import_creates_cases_and_reports_bad_rows(client, db_session, auth_headers_admin):
    files = {"file": ("export.json", json.dumps(CCTNS_RECORDS).encode(), "application/json")}
    report = (await client.post("/api/v1/integrations/cctns/import", headers=auth_headers_admin, files=files)).json()
    # Record 2 has no coordinates and is placed at its district's centre (record 1 is in the same district);
    # record 3's latitude is unreadable, which is reported rather than guessed.
    assert report["created"] == 2 and report["error_count"] == 1 and report["errors"][0]["row"] == 3

    crime = (await db_session.execute(select(Crime).where(Crime.case_number == "CCTNS/Hauz Khas/0412/2026"))).scalar_one()
    assert crime.legal_sections == ["309(4)", "3(5)"] and crime.accused_first_remanded_at is not None
    placed = (await db_session.execute(select(Crime).where(Crime.case_number == "CCTNS/Saket/0413/2026"))).scalar_one()
    assert (placed.latitude, placed.longitude) == (crime.latitude, crime.longitude)

    again = (await client.post("/api/v1/integrations/cctns/import", headers=auth_headers_admin, files=files)).json()
    assert again["created"] == 0 and again["skipped"] == 2


async def test_seizure_without_recording_is_flagged_until_a_sid_is_linked(client, db_session, auth_headers_police):
    crime = Crime(crime_type="theft", severity=2, city="Delhi", district="South", latitude=28.5, longitude=77.2,
                  occurred_at=datetime.now(UTC) - timedelta(days=3), case_number="DL-SEIZE-1",
                  description="The stolen phone was recovered from the accused and seized.")
    db_session.add(crime)
    await db_session.commit()
    dossier = f"/api/v1/crimes/{crime.id}/dossier"

    assert "s.105" in (await client.get(dossier, headers=auth_headers_police)).json()["evidence"]["s105_gap"]

    bad = await client.post(f"/api/v1/integrations/esakshya/{crime.id}/links", headers=auth_headers_police,
                            json={"sid": "not-a-session-id", "provision": "105"})
    assert bad.status_code == 422
    good = await client.post(f"/api/v1/integrations/esakshya/{crime.id}/links", headers=auth_headers_police,
                             json={"sid": "1234 5678 9012 3456", "provision": "105", "packet_hash": "ab" * 32})
    assert good.status_code == 201 and good.json()["sid"] == "1234567890123456"

    evidence = (await client.get(dossier, headers=auth_headers_police)).json()["evidence"]
    assert evidence["s105_gap"] is None and len(evidence["links"]) == 1

    enrichment = (await client.get(f"/api/v1/integrations/cctns/enrichment/{crime.id}", headers=auth_headers_police)).json()
    assert enrichment["schema"] == "crimeai.cctns-enrichment.v1" and enrichment["evidence"]["links"][0]["provision"] == "105"
