"""Investigation intelligence: a case's documents, contradictions, timeline and officer reviews."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Analyst, Officer
from app.db.session import get_db
from app.meko import contract
from app.meko import service as meko
from app.nlp import gemini
from app.services import custody, investigation_case
from app.services.audit_service import record_audit

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class DocumentIn(BaseModel):
    doc_type: str = Field(..., max_length=30)
    title: str = Field(..., min_length=3, max_length=200)
    text: str = Field(..., min_length=10, max_length=20000)
    recorded_at: datetime | None = None
    source_ref: str | None = Field(None, max_length=120)


class ReviewIn(BaseModel):
    decision: Literal["accepted", "rejected", "needs_investigation", "open"]
    note: str = Field("", max_length=1000)


@router.get("/cases/{crime_id}", summary="Documents, contradictions, timeline and approved context for one case")
async def case_view(crime_id: uuid.UUID, user: Analyst, db: DbDep, meko_on: bool = Query(True, alias="meko")) -> dict:
    return await investigation_case.case_view(db, crime_id, with_meko=meko_on)


@router.get("/cases/{crime_id}/approved-context", summary="Approved findings from earlier cases, recalled from Meko")
async def approved_context(crime_id: uuid.UUID, user: Analyst, db: DbDep) -> dict:
    return await investigation_case.approved_context(db, crime_id)


@router.post("/cases/{crime_id}/documents", status_code=status.HTTP_201_CREATED,
             summary="Add a statement, report or memo to a case (personal identifiers are redacted before storage)")
async def add_document(crime_id: uuid.UUID, body: DocumentIn, request: Request, user: Officer, db: DbDep) -> dict:
    doc = await investigation_case.add_document(
        db, crime_id, doc_type=body.doc_type, title=body.title, text=body.text, recorded_at=body.recorded_at,
        source_ref=body.source_ref, user_id=user.user_id)
    await record_audit(db, request, user, action="investigation.document_added", resource_type="crime",
                       resource_id=str(crime_id), metadata={"document": str(doc.id), "type": body.doc_type})
    return {"id": str(doc.id)}


@router.delete("/cases/{crime_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(crime_id: uuid.UUID, document_id: uuid.UUID, request: Request, user: Officer, db: DbDep) -> None:
    await investigation_case.delete_document(db, crime_id, document_id)
    await record_audit(db, request, user, action="investigation.document_removed", resource_type="crime",
                       resource_id=str(crime_id), metadata={"document": str(document_id)})


@router.post("/cases/{crime_id}/findings/{fingerprint}/review",
             summary="Accept, reject or send a finding for further investigation (accepted findings become Meko context)")
async def review(crime_id: uuid.UUID, fingerprint: str, body: ReviewIn, request: Request, user: Officer, db: DbDep) -> dict:
    agency = contract.AGENCIES.get(meko.AGENCY, meko.AGENCY)
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    result = await investigation_case.review_finding(
        db, crime_id, fingerprint[:64], decision=body.decision, note=body.note, user_id=user.user_id,
        decided_by=f"{role} officer, {agency}")
    await record_audit(db, request, user, action="investigation.finding_reviewed", resource_type="crime",
                       resource_id=str(crime_id), metadata={"finding": fingerprint[:64], "decision": body.decision,
                                                            "meko": result["meko"].get("status")})
    return result


@router.post("/cases/{crime_id}/gemini",
             summary="Gemini explains each finding and drafts next steps (identifiers redacted before sending, audited)")
async def gemini_review(crime_id: uuid.UUID, request: Request, user: Analyst, db: DbDep) -> dict:
    if not gemini.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Gemini is not configured on this server")
    review = await investigation_case.gemini_review(db, crime_id)
    await record_audit(db, request, user, action="investigation.gemini_review", resource_type="crime",
                       resource_id=str(crime_id), metadata={"model": review["model"], "chars_sent": review["chars_sent"],
                                                            "redactions": review["redactions"]})
    return review


@router.get("/cases/{crime_id}/seals", summary="Chain of custody: this case's seals on Solana")
async def list_seals(crime_id: uuid.UUID, user: Analyst, db: DbDep) -> dict:
    return {**custody.status(), "seals": await custody.list_seals(db, crime_id)}


@router.post("/cases/{crime_id}/seals", status_code=status.HTTP_201_CREATED,
             summary="Seal the case file: hash every document and review, anchor the Merkle root on Solana")
async def seal_case(crime_id: uuid.UUID, request: Request, user: Officer, db: DbDep) -> dict:
    if not custody.status()["enabled"]:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Solana sealing is not configured on this server")
    sealed = await custody.seal(db, crime_id, user.user_id)
    await record_audit(db, request, user, action="investigation.case_sealed", resource_type="crime",
                       resource_id=str(crime_id), metadata={"seal": sealed["id"], "root": sealed["merkle_root"],
                                                            "signature": sealed["signature"], "status": sealed["status"]})
    return sealed


@router.get("/cases/{crime_id}/seals/{seal_id}/verify",
            summary="Recompute the case file's hashes and check them against the seal and the chain")
async def verify_seal(crime_id: uuid.UUID, seal_id: uuid.UUID, user: Analyst, db: DbDep) -> dict:
    return await custody.verify(db, crime_id, seal_id)
