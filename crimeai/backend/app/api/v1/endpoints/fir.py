"""
FIR intake and analysis.

Investigating officers see the original narrative. Analysts see the PII-redacted
copy: they need the modus operandi, not the complainant's Aadhaar number.
"""

import re
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Analyst, CurrentUser, Officer
from app.api.v1.uploads import read_capped
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.rate_limit import limiter
from app.core.security import UserRole
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.fir import FIRReport
from app.nlp import gemini
from app.nlp.multilingual import analyse
from app.repositories.fir_repository import FIRRepository
from app.schemas.fir import FIR_NUMBER_PATTERN, FIRCreateRequest, FIRListResponse, FIRResponse, normalise_fir_number
from app.services.audit_service import record_audit
from app.services.nlp_service import NLPService
from app.services.storage import load_document

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _service(db: DbDep, redis: Annotated[Redis, Depends(get_redis)]) -> NLPService:
    return NLPService(db, redis)


ServiceDep = Annotated[NLPService, Depends(_service)]


def to_response(fir: FIRReport, viewer: CurrentUser, with_highlights: bool = False) -> FIRResponse:
    sees_original = viewer.can(UserRole.POLICE)
    text = fir.raw_text if sees_original else (fir.redacted_text or "[narrative withheld until redaction completes]")
    return FIRResponse(
        id=fir.id,
        fir_number=fir.fir_number,
        crime_id=fir.crime_id,
        submitted_by=fir.submitted_by,
        incident_date=fir.incident_date,
        text=text,
        text_redacted=not sees_original,
        file_type=fir.file_type,
        file_sha256=fir.file_sha256,
        extracted_entities=fir.extracted_entities,
        extraction_confidence=fir.extraction_confidence,
        nlp_status=fir.nlp_status,
        nlp_error=fir.nlp_error if sees_original else None,
        language=fir.language,
        highlights=[asdict(h) for h in analyse(text).highlights] if with_highlights and text else None,
        has_document=bool(fir.file_url) and sees_original,
        created_at=fir.created_at,
        updated_at=fir.updated_at,
    )


@router.get("/", response_model=FIRListResponse)
async def list_firs(
    user: Analyst,
    db: DbDep,
    nlp_status: str | None = Query(None),
    my_reports: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FIRListResponse:
    items, total = await FIRRepository(db).list_firs(
        nlp_status=nlp_status, submitted_by=user.user_id if my_reports else None, limit=limit, offset=offset
    )
    return FIRListResponse(items=[to_response(f, user) for f in items], total=total)


@router.post("/", response_model=FIRResponse, status_code=status.HTTP_201_CREATED)
async def submit_fir(body: FIRCreateRequest, user: Officer, service: ServiceDep) -> FIRResponse:
    fir = await service.submit_text(
        body.fir_number, body.raw_text, user.user_id, crime_id=body.crime_id, incident_date=body.incident_date
    )
    return to_response(fir, user)


@router.post("/upload", response_model=FIRResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def upload_fir(
    request: Request,
    user: Officer,
    service: ServiceDep,
    fir_number: Annotated[str, Form(max_length=200)],
    file: Annotated[UploadFile, File()],
    crime_id: Annotated[uuid.UUID | None, Form()] = None,
    incident_date: Annotated[datetime | None, Form()] = None,
) -> FIRResponse:
    fir_number = normalise_fir_number(fir_number)
    if not re.fullmatch(FIR_NUMBER_PATTERN, fir_number):
        raise ValidationError("FIR number needs at least 3 letters or digits, e.g. 14/2018 or PS-0014-2018")
    data = await read_capped(file, settings.MAX_UPLOAD_BYTES)
    fir = await service.submit_document(
        fir_number, file.filename, data, user.user_id, crime_id=crime_id, incident_date=incident_date
    )
    return to_response(fir, user)


@router.get("/{fir_id}", response_model=FIRResponse)
async def get_fir(fir_id: uuid.UUID, request: Request, user: Analyst, db: DbDep) -> FIRResponse:
    fir = await FIRRepository(db).get_by_id(fir_id)
    if fir is None:
        raise NotFoundError("FIR not found")
    if user.can(UserRole.POLICE):
        await record_audit(db, request, user, action="fir.read_original", resource_type="fir", resource_id=str(fir_id))
    return to_response(fir, user, with_highlights=True)


@router.get("/{fir_id}/document", summary="Original uploaded document (police and above, audited)")
async def get_fir_document(fir_id: uuid.UUID, request: Request, user: Officer, db: DbDep) -> Response:
    fir = await FIRRepository(db).get_by_id(fir_id)
    if fir is None or not fir.file_url:
        raise NotFoundError("No document attached to this FIR")
    data = await load_document(fir.file_url)
    await record_audit(db, request, user, action="fir.read_document", resource_type="fir", resource_id=str(fir_id))
    return Response(
        data,
        media_type=fir.file_type or "application/octet-stream",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": f'inline; filename="{fir.fir_number.replace("/", "-")}"'},
    )


@router.post(
    "/{fir_id}/gemini-brief",
    summary="English translation and brief of this FIR by Gemini (PII redacted before sending, audited, cached)",
)
@limiter.limit("10/minute")
async def gemini_brief(
    fir_id: uuid.UUID, request: Request, user: Analyst, db: DbDep, refresh: bool = Query(False),
) -> dict:
    fir = await FIRRepository(db).get_by_id(fir_id)
    if fir is None:
        raise NotFoundError("FIR not found")
    cached = (fir.extracted_entities or {}).get("gemini")
    if cached and not refresh:
        return cached
    if not gemini.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Gemini is not configured on this server")
    if not (fir.raw_text or "").strip():
        raise ValidationError("This FIR has no text yet; wait for OCR to finish")
    brief = await gemini.case_brief(fir.raw_text, fir.incident_date)
    # Reassign rather than mutate: the JSON column only notices a new value.
    fir.extracted_entities = {**(fir.extracted_entities or {}), "gemini": brief}
    await record_audit(db, request, user, action="fir.gemini_brief", resource_type="fir", resource_id=str(fir_id),
                       metadata={"model": brief["model"], "chars_sent": brief["chars_sent"],
                                 "redactions": brief["redactions"]})
    return brief


@router.post("/{fir_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_fir(fir_id: uuid.UUID, user: Analyst, service: ServiceDep) -> dict:
    if await service.firs.get_by_id(fir_id) is None:
        raise NotFoundError("FIR not found")
    task_id = await service.reprocess(fir_id)
    return {"message": "Reprocessing queued", "task_id": task_id}
