"""
File importers for CCTNS FIR exports and NCRP cyber-fraud complaints.

Both accept JSON (an array of records) or CSV with the column names documented in
docs/INTEGRATIONS.md. Imports are idempotent: a record whose FIR number or NCRP
acknowledgement number is already present is skipped, so a nightly export can be
re-imported in full. Each record succeeds or fails on its own; the report lists
every failure with its row number.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import Crime
from app.nlp.legal.bns_crosswalk import analyse_sections
from app.nlp.parsers.crime_classifier import classify_crime_type
from app.repositories.fir_repository import FIRRepository
from app.services import entity_graph
from app.workers.dispatch import enqueue

MAX_RECORDS = 5000
_SECTION = re.compile(r"\d{1,3}[A-Z]?(?:\(\d+[a-z]?\))*", re.I)


@dataclass(slots=True)
class ImportReport:
    received: int = 0
    created: int = 0
    skipped: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    linked_entities: set[uuid.UUID] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {"received": self.received, "created": self.created, "skipped": self.skipped,
                "errors": self.errors[:50], "error_count": len(self.errors)}


def parse_records(data: bytes, filename: str | None) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig")
    if (filename or "").lower().endswith(".json") or text.lstrip().startswith("["):
        records = json.loads(text)
        if not isinstance(records, list):
            raise ValueError("JSON import must be an array of records")
    else:
        records = list(csv.DictReader(io.StringIO(text)))
    if len(records) > MAX_RECORDS:
        raise ValueError(f"At most {MAX_RECORDS} records per file")
    return [{k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k} for r in records]


def _date(value: Any, field_name: str, required: bool = False) -> datetime | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _district_centre(db: AsyncSession, district: str | None) -> tuple[float, float] | None:
    """Where a record has no coordinates, place it at the incident-weighted centre of its district."""
    if not district:
        return None
    row = (await db.execute(
        select(func.avg(Crime.latitude), func.avg(Crime.longitude)).where(func.lower(Crime.district) == district.lower())
    )).one()
    return (float(row[0]), float(row[1])) if row[0] is not None else None


async def _location(db: AsyncSession, record: dict[str, Any]) -> tuple[float, float]:
    lat, lng = record.get("latitude"), record.get("longitude")
    if lat not in (None, "") or lng not in (None, ""):
        # Coordinates that are present but unreadable are an error, not a reason to guess the district centre.
        try:
            lat_f, lng_f = float(lat), float(lng)
        except (TypeError, ValueError):
            raise ValueError("latitude and longitude must both be numbers") from None
        if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
            raise ValueError("latitude/longitude out of range")
        return lat_f, lng_f
    centre = await _district_centre(db, record.get("district"))
    if centre is None:
        raise ValueError("latitude/longitude missing and the district has no incidents to place it by")
    return centre


async def import_cctns(db: AsyncSession, records: list[dict[str, Any]], user_id: uuid.UUID) -> ImportReport:
    """CCTNS FIRs become cases plus FIR narratives; the NLP worker then reads, maps and links them."""
    from app.services.nlp_service import NLPService

    report = ImportReport(received=len(records))
    firs = FIRRepository(db)
    nlp = NLPService(db, None)
    for row, record in enumerate(records, start=1):
        try:
            fir_number = str(record.get("fir_number") or "").strip()
            facts = str(record.get("brief_facts") or "").strip()
            if not fir_number or not facts:
                raise ValueError("fir_number and brief_facts are required")
            if await firs.get_by_fir_number(fir_number):
                report.skipped += 1
                continue
            occurred = _date(record.get("occurred_at"), "occurred_at", required=True)
            lat, lng = await _location(db, record)
            sections_text = record.get("acts_sections") or ""
            if isinstance(sections_text, list):
                sections_text = ", ".join(sections_text)
            legal = analyse_sections(f"{sections_text} {facts}", occurred)
            crime_type = next((m["crime_type"] for m in legal["mapped"] if m.get("crime_type")), None) \
                or classify_crime_type(facts)["crime_type"]
            async with db.begin_nested():
                crime = Crime(
                    crime_type=crime_type, severity=3, latitude=lat, longitude=lng,
                    district=record.get("district") or None, city=record.get("city") or record.get("district") or "Unknown",
                    location_name=record.get("place_of_occurrence") or None, occurred_at=occurred,
                    description=facts[:5000], case_number=f"CCTNS/{record.get('police_station') or 'PS'}/{fir_number}"[:50],
                    legal_sections=[s.upper() for s in _SECTION.findall(sections_text)][:20] or None,
                    accused_arrested_at=_date(record.get("accused_arrested_at"), "accused_arrested_at"),
                    accused_first_remanded_at=_date(record.get("first_remanded_at"), "first_remanded_at"),
                    chargesheet_filed_at=_date(record.get("chargesheet_filed_at"), "chargesheet_filed_at"),
                    status="under_investigation",
                )
                db.add(crime)
                await db.flush()
            await nlp.submit_text(fir_number, facts, user_id, crime_id=crime.id, incident_date=occurred)
            enqueue("app.workers.tasks.ml_tasks.embed_crime", str(crime.id))
            report.created += 1
        except Exception as exc:
            report.errors.append({"row": row, "error": str(exc)[:200]})
    return report


async def import_ncrp(db: AsyncSession, records: list[dict[str, Any]]) -> ImportReport:
    """NCRP complaints become cyber-fraud cases linked straight into the identifier graph."""
    report = ImportReport(received=len(records))
    for row, record in enumerate(records, start=1):
        try:
            ack = str(record.get("acknowledgement_no") or "").strip()
            if not ack:
                raise ValueError("acknowledgement_no is required")
            case_number = f"NCRP-{ack}"[:50]
            if (await db.execute(select(Crime.id).where(Crime.case_number == case_number))).first():
                report.skipped += 1
                continue
            occurred = _date(record.get("complaint_date"), "complaint_date", required=True)
            lat, lng = await _location(db, record)
            amount = record.get("amount")
            parts = [str(record.get("description") or record.get("category") or "Cyber-financial fraud complaint").strip()]
            if amount not in (None, ""):
                parts.append(f"Amount lost: Rs {amount}.")
            for label, key in (("Suspect UPI ID", "suspect_upi"), ("Suspect mobile", "suspect_phone"),
                               ("Suspect A/c No.", "suspect_account")):
                if record.get(key):
                    parts.append(f"{label}: {record[key]}.")
            description = " ".join(parts)
            category = str(record.get("category") or "").lower()
            async with db.begin_nested():
                crime = Crime(
                    crime_type="fraud" if any(w in category for w in ("fraud", "upi", "bank", "investment")) else "cybercrime",
                    severity=3, latitude=lat, longitude=lng, district=record.get("district") or None,
                    city=record.get("city") or record.get("district") or "Unknown", occurred_at=occurred,
                    description=description[:5000], case_number=case_number, status="reported",
                )
                db.add(crime)
                await db.flush()
                identifiers = entity_graph.identifiers_in(description)
                if record.get("suspect_account"):
                    identifiers.append(entity_graph.account_identifier(re.sub(r"\D", "", str(record["suspect_account"]))))
                report.linked_entities.update(
                    await entity_graph.link_identifiers(db, crime.id, identifiers, occurred_at=occurred, source="ncrp")
                )
            enqueue("app.workers.tasks.ml_tasks.embed_crime", str(crime.id))
            report.created += 1
        except Exception as exc:
            report.errors.append({"row": row, "error": str(exc)[:200]})
    return report
