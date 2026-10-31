"""
A case's investigation view: its documents, the agents' findings with officers' reviews, the timeline, and the
approved context Meko recalls from earlier investigations.

The view is computed live, so a GET never writes. A finding is stored only once an officer reviews it, keyed by
its fingerprint, so the review survives re-analysis and later document edits.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.integrations import esakshya
from app.meko import contract
from app.meko import service as meko
from app.models.audit_log import AuditLog
from app.models.crime import Crime
from app.models.fir import FIRReport
from app.models.investigation import DOCUMENT_TYPES, REVIEW_STATUSES, CaseDocument, InvestigationFinding
from app.nlp import gemini
from app.nlp.legal.bns_crosswalk import analyse_sections
from app.nlp.multilingual import analyse, normalise_for_legal
from app.nlp.privacy.redaction import redact
from app.services import entity_graph
from app.services.investigation import Doc, investigate


async def _crime(db: AsyncSession, crime_id: uuid.UUID) -> Crime:
    crime = await db.get(Crime, crime_id)
    if crime is None:
        raise NotFoundError("Case not found")
    return crime


async def _documents(db: AsyncSession, crime: Crime) -> tuple[list[Doc], list[dict[str, Any]], str]:
    """The FIR (redacted) plus every case document, as agent inputs and as rows for the screen."""
    fir = (await db.execute(
        select(FIRReport).where(FIRReport.crime_id == crime.id).order_by(FIRReport.created_at).limit(1)
    )).scalar_one_or_none()
    docs: list[Doc] = []
    rows: list[dict[str, Any]] = []
    narrative = ""
    if fir is not None:
        narrative = fir.redacted_text or redact(fir.raw_text).text
        docs.append(Doc(f"fir:{fir.id}", f"FIR {fir.fir_number}", "fir", narrative, fir.created_at))
    elif crime.description:
        narrative = redact(crime.description).text
        docs.append(Doc(f"case:{crime.id}", "Case narrative", "fir", narrative, crime.reported_at))
    for doc in docs:
        rows.append({"id": doc.id, "doc_type": doc.doc_type, "type_label": DOCUMENT_TYPES[doc.doc_type],
                     "title": doc.title, "recorded_at": doc.recorded_at.isoformat() if doc.recorded_at else None,
                     "language": analyse(doc.text).language, "text": doc.text, "source_ref": None, "removable": False})
    for d in (await db.execute(
        select(CaseDocument).where(CaseDocument.crime_id == crime.id).order_by(CaseDocument.recorded_at, CaseDocument.created_at)
    )).scalars():
        docs.append(Doc(str(d.id), d.title, d.doc_type, d.text, d.recorded_at))
        rows.append({"id": str(d.id), "doc_type": d.doc_type, "type_label": DOCUMENT_TYPES.get(d.doc_type, d.doc_type),
                     "title": d.title, "recorded_at": d.recorded_at.isoformat() if d.recorded_at else None,
                     "language": d.language, "text": d.text, "source_ref": d.source_ref, "removable": True})
    return docs, rows, narrative


async def document_rows(db: AsyncSession, crime: Crime) -> list[dict[str, Any]]:
    """The case's documents as stored: the FIR (redacted) or case narrative, then every case document."""
    return (await _documents(db, crime))[1]


def case_ref(crime: Crime) -> str:
    return contract.case_ref(meko.AGENCY, crime.case_number or str(crime.id)[:8])


def _vehicle_tokens(findings: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[str]:
    plates = {c["value"] for c in claims if c["subject"] == "vehicle"}
    plates |= {c["value"] for f in findings for c in f["claims"] if c["subject"] == "vehicle"}
    return sorted(contract.fingerprint("vehicle", p) for p in plates)


async def _analysis(db: AsyncSession, crime: Crime) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    docs, rows, narrative = await _documents(db, crime)
    evidence = [esakshya.link_to_dict(link) for link in await esakshya.list_links(db, crime.id)]
    case = {k: getattr(crime, k) for k in ("occurred_at", "accused_arrested_at", "accused_first_remanded_at",
                                           "chargesheet_filed_at")}
    return investigate(case, docs, evidence), rows, narrative


async def case_view(db: AsyncSession, crime_id: uuid.UUID, with_meko: bool = True) -> dict[str, Any]:
    crime = await _crime(db, crime_id)
    result, rows, narrative = await _analysis(db, crime)
    reviewed = {f.fingerprint: f for f in (await db.execute(
        select(InvestigationFinding).where(InvestigationFinding.crime_id == crime_id))).scalars()}
    for f in result["findings"]:
        r = reviewed.get(f["fingerprint"])
        f.update({"status": r.status if r else "open", "review_note": r.review_note if r else None,
                  "reviewed_at": r.reviewed_at.isoformat() if r and r.reviewed_at else None})

    linked = await entity_graph.entities_for_crime(db, crime_id)
    legal = analyse_sections(normalise_for_legal(narrative), crime.occurred_at) if narrative else None
    audited = (await db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.resource_id == str(crime_id)))).scalar_one()
    contradictions = [f for f in result["findings"] if f["kind"] == "contradiction"]
    gaps = [f for f in result["findings"] if f["kind"] == "gap"]
    agents = [
        {"name": "FIR intelligence", "summary": f"{len(rows)} document(s) read; language {analyse(narrative).language_name if narrative else 'n/a'}"},
        {"name": "Evidence intelligence", "summary": f"{len(result['claims'])} claim(s) compared; {len(contradictions)} contradiction(s)"},
        {"name": "Case linking", "summary": f"{sum(1 for e in linked if (e.get('case_count') or 0) > 1)} identifier(s) shared with other cases"},
        {"name": "Timeline", "summary": f"{len(result['timeline'])} dated event(s); {len(gaps)} gap(s) of {result['gap_days']}+ days"},
        {"name": "Legal intelligence", "summary": f"{len((legal or {}).get('mapped', []))} section(s) mapped; {len((legal or {}).get('warnings', []))} warning(s)"},
        {"name": "Audit", "summary": f"{audited} audited action(s) on this case; every finding cites its source"},
    ]

    ref = case_ref(crime)
    recalled = await _approved(db, crime, result) if with_meko else {"status": "off", "items": [], "calls": []}
    return {"case_ref": ref, "documents": rows, "agents": agents, **result, "meko": recalled,
            "review_statuses": list(REVIEW_STATUSES)}


async def _approved(db: AsyncSession, crime: Crime, result: dict[str, Any]) -> dict[str, Any]:
    if not settings.meko_enabled:
        return {"status": "off", "items": [], "calls": []}
    return await meko.recall_approved(db, case_ref=case_ref(crime), tokens=_vehicle_tokens(result["findings"], result["claims"]),
                                      crime_type=crime.crime_type)


async def approved_context(db: AsyncSession, crime_id: uuid.UUID) -> dict[str, Any]:
    """Meko's approved findings from earlier cases that mention this case's vehicles, fetched on its own so the
    case view does not wait on Meko."""
    crime = await _crime(db, crime_id)
    result, _, _ = await _analysis(db, crime)
    return await _approved(db, crime, result)


async def add_document(db: AsyncSession, crime_id: uuid.UUID, *, doc_type: str, title: str, text: str,
                       recorded_at: datetime | None, source_ref: str | None, user_id: uuid.UUID) -> CaseDocument:
    await _crime(db, crime_id)
    if doc_type not in DOCUMENT_TYPES or doc_type == "fir":
        raise ValidationError(f"Document type must be one of {', '.join(k for k in DOCUMENT_TYPES if k != 'fir')}")
    clean = redact(text).text
    doc = CaseDocument(crime_id=crime_id, doc_type=doc_type, title=title.strip()[:200], text=clean,
                       recorded_at=recorded_at, language=analyse(clean).language,
                       source_ref=(source_ref or "").strip()[:120] or None, added_by=user_id)
    db.add(doc)
    await db.flush()
    return doc


async def delete_document(db: AsyncSession, crime_id: uuid.UUID, document_id: uuid.UUID) -> None:
    doc = await db.get(CaseDocument, document_id)
    if doc is None or doc.crime_id != crime_id:
        raise NotFoundError("Document not found")
    await db.delete(doc)
    await db.flush()


async def review_finding(db: AsyncSession, crime_id: uuid.UUID, fingerprint: str, *, decision: str, note: str,
                         user_id: uuid.UUID, decided_by: str) -> dict[str, Any]:
    if decision not in REVIEW_STATUSES:
        raise ValidationError(f"Decision must be one of {', '.join(REVIEW_STATUSES)}")
    crime = await _crime(db, crime_id)
    result, _, _ = await _analysis(db, crime)
    finding = next((f for f in result["findings"] if f["fingerprint"] == fingerprint), None)
    if finding is None:
        raise NotFoundError("Finding not found: the documents may have changed; reload the case")
    now = datetime.now(UTC)
    clean_note = redact(note or "").text.strip()[:1000] or None
    await db.execute(
        insert(InvestigationFinding)
        .values(crime_id=crime_id, fingerprint=fingerprint, agent=finding["agent"], kind=finding["kind"],
                title=finding["title"][:300], detail=finding, status=decision, review_note=clean_note,
                reviewed_by=user_id, reviewed_at=now)
        .on_conflict_do_update(
            constraint="uq_investigation_findings_crime_fingerprint",
            set_={"status": decision, "review_note": clean_note, "reviewed_by": user_id, "reviewed_at": now,
                  "detail": finding, "title": finding["title"][:300]},
        )
    )
    shared: dict[str, Any] = {"status": "off"}
    if decision == "accepted" and settings.meko_enabled:
        shared = await meko.save_approved_finding(
            db, case_ref=case_ref(crime), finding=finding, tokens=_vehicle_tokens([finding], []), decided_by=decided_by)
    return {"fingerprint": fingerprint, "status": decision, "review_note": clean_note, "reviewed_at": now.isoformat(),
            "meko": shared}


async def gemini_review(db: AsyncSession, crime_id: uuid.UUID) -> dict[str, Any]:
    """Gemini's explanation of each finding and a draft plan, over the same documents the agents read."""
    crime = await _crime(db, crime_id)
    result, rows, _ = await _analysis(db, crime)
    case = {"crime_type": crime.crime_type, "district": crime.district,
            "occurred_at": crime.occurred_at.isoformat() if crime.occurred_at else None}
    return await gemini.investigation_review(case, result["findings"], rows)
