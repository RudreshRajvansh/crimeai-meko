"""
Consolidated freeze/lien request for a UPI ID, account or phone that links several fraud complaints.

Mule accounts are emptied within hours, and every complaint that names one is
usually filed and chased separately. This assembles one request citing all
linked complaints, with the amounts and the time since the latest complaint,
for the investigating officer to review and send. Nothing is sent from here.

Identifiers are stored only as keyed hashes. The full value a bank needs is
recovered by re-reading the linked narratives and matching the hash; it is
returned only to police roles and the read is audited by the caller.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.crime import Crime
from app.models.entity import Entity, EntityMention
from app.models.fir import FIRReport
from app.nlp.multilingual import analyse
from app.services.entity_graph import _keyed, accounts_in

FREEZABLE_KINDS = {"upi", "account", "phone"}
_LEGAL_BASIS = (
    "BNSS s.106 (formerly CrPC s.102): seizure of property suspected to be connected with an offence. "
    "Confirm the provision and any reporting duty with the legal cell before sending; for cyber-financial "
    "fraud also record the lien request on the I4C Citizen Financial Cyber Fraud Reporting and Management System."
)


def _full_identifier(kind: str, key: str, texts: list[str]) -> str | None:
    for text in texts:
        analysis = analyse(text)
        candidates = analysis.upi_ids if kind == "upi" else analysis.phones if kind == "phone" else accounts_in(text)
        for value in candidates:
            if _keyed(value) == key:
                return value
    return None


def _complaint_line(index: int, complaint: dict[str, Any]) -> str:
    reference = complaint["case_number"] or complaint["crime_id"][:8]
    if complaint["fir_numbers"]:
        reference += " / FIR " + ", ".join(complaint["fir_numbers"])
    parts = [reference, datetime.fromisoformat(complaint["occurred_at"]).strftime("%d %b %Y"),
             complaint["district"] or "district not recorded"]
    if complaint["amount"]:
        parts.append(f"Rs {complaint['amount']:,.0f}")
    return f"  {index}. " + ", ".join(parts)


def _largest_amount(texts: list[str]) -> float | None:
    amounts = [a for t in texts for a in analyse(t).amounts]
    return max(amounts) if amounts else None


async def build_packet(db: AsyncSession, entity_id: uuid.UUID, officer_name: str | None = None) -> dict[str, Any]:
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise NotFoundError("Identifier not found")
    if entity.kind not in FREEZABLE_KINDS:
        raise ValidationError("A freeze request applies to a UPI ID, bank account or phone number")

    crimes = (await db.execute(
        select(Crime).join(EntityMention, EntityMention.crime_id == Crime.id)
        .where(EntityMention.entity_id == entity_id).order_by(Crime.occurred_at)
    )).scalars().all()
    if not crimes:
        raise NotFoundError("No complaints are linked to this identifier")
    firs = (await db.execute(select(FIRReport).where(FIRReport.crime_id.in_([c.id for c in crimes])))).scalars().all()
    fir_by_crime: dict[uuid.UUID, list[FIRReport]] = {}
    for fir in firs:
        fir_by_crime.setdefault(fir.crime_id, []).append(fir)

    complaints, all_texts = [], []
    for crime in crimes:
        texts = [crime.description or ""] + [f.raw_text or "" for f in fir_by_crime.get(crime.id, [])]
        all_texts += texts
        complaints.append({
            "crime_id": str(crime.id),
            "case_number": crime.case_number,
            "fir_numbers": [f.fir_number for f in fir_by_crime.get(crime.id, [])],
            "occurred_at": crime.occurred_at.isoformat(),
            "district": crime.district,
            "crime_type": crime.crime_type,
            # Largest amount named in the case; summing every mention would double-count repeated figures.
            "amount": _largest_amount(texts),
        })

    latest = max(c.occurred_at for c in crimes)
    total = sum(c["amount"] or 0 for c in complaints)
    identifier = _full_identifier(entity.kind, entity.key, all_texts)
    noun = {"upi": "UPI ID", "account": "bank account", "phone": "mobile number"}[entity.kind]
    shown = identifier or f"{entity.label} (full value: see the linked FIRs)"
    lines = "\n".join(_complaint_line(i, c) for i, c in enumerate(complaints, 1))
    target = "the bank account(s) linked to it" if entity.kind == "phone" else "it"
    loss = f", with a reported loss of Rs {total:,.0f}" if total else ""
    signature = "[Name, rank and police station]" + (f" ({officer_name})" if officer_name else "")
    draft = (
        f"To: The Nodal Officer, [bank / payment service provider]\n\n"
        f"Subject: Request to debit-freeze / mark lien on {noun} {shown}, linked to {len(complaints)} complaints\n\n"
        f"The {noun} {shown} is named in the following {len(complaints)} complaints registered between "
        f"{crimes[0].occurred_at:%d %b %Y} and {latest:%d %b %Y}{loss}:\n{lines}\n\n"
        f"You are requested to immediately debit-freeze / mark lien on {target} to the extent of the reported "
        f"amounts, preserve KYC, transaction and IP/device logs from {crimes[0].occurred_at:%d %b %Y} to date, "
        f"and share the beneficiary trail of onward transfers.\n\n"
        f"Legal basis: {_LEGAL_BASIS}\n\n"
        f"{signature}\n[Date]"
    )
    return {
        "entity": {"id": str(entity.id), "kind": entity.kind, "label": entity.label, "identifier": identifier},
        "complaints": complaints,
        "totals": {
            "complaints": len(complaints),
            "districts": sorted({c.district for c in crimes if c.district}),
            "amount": total or None,
            "first": crimes[0].occurred_at.isoformat(),
            "latest": latest.isoformat(),
            "hours_since_latest": round((datetime.now(UTC) - latest).total_seconds() / 3600, 1),
        },
        "draft": draft,
        "legal_basis": _LEGAL_BASIS,
    }
