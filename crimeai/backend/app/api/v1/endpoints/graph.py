"""Link analysis: identifiers (vehicles, phones, UPI IDs) that connect separate cases."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Analyst, Officer
from app.core.exceptions import NotFoundError, ValidationError
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.services import entity_graph
from app.services.audit_service import record_audit
from app.services.freeze_packet import build_packet

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/overview", summary="Every identifier linking two or more cases, with those cases and active series")
async def graph_overview(user: Analyst, db: DbDep, min_cases: int = Query(2, ge=2, le=20)) -> dict:
    return await entity_graph.overview(db, min_cases=min_cases)


@router.get("/neighbourhood", summary="Expand around a case, entity or series node")
async def graph_neighbourhood(
    user: Analyst,
    db: DbDep,
    node: str = Query(..., pattern=r"^(crime|entity):[0-9a-f-]{36}$|^series:SER-[0-9A-F]{10}$"),
    depth: int = Query(2, ge=1, le=4),
) -> dict:
    try:
        return await entity_graph.neighbourhood(db, node, depth)
    except ValueError as exc:
        raise ValidationError("Invalid node id") from exc


@router.get("/case-map/{crime_id}", summary="One case and every case it matches, placed for the map")
async def case_map(crime_id: uuid.UUID, user: Analyst, db: DbDep) -> dict:
    result = await entity_graph.case_map(db, crime_id)
    if not result:
        raise NotFoundError("Case not found")
    return result


@router.get("/search", summary="Find a vehicle number, phone number or UPI ID in the link graph")
async def graph_search(user: Analyst, db: DbDep, q: str = Query(..., min_length=2, max_length=64)) -> list[dict]:
    return await entity_graph.search(db, q)


class CheckRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10000)


@router.post("/check", summary="Which phones, UPI IDs, accounts or vehicles in this text are already on record (read-only, audited)")
@limiter.limit("30/minute")
async def graph_check(request: Request, body: CheckRequest, user: Officer, db: DbDep) -> dict:
    result = await entity_graph.check_text(db, body.text)
    await record_audit(db, request, user, action="graph.check", resource_type="fir_text",
                       metadata={"identifiers": result["identifiers"], "known": result["known"]})
    return result


@router.get(
    "/entities/{entity_id}/freeze-packet",
    summary="Draft one freeze/lien request citing every complaint linked to a UPI ID, account or phone (audited)",
)
async def freeze_packet(entity_id: uuid.UUID, request: Request, user: Officer, db: DbDep) -> dict:
    packet = await build_packet(db, entity_id)
    # The packet reveals the full identifier recovered from the FIRs, so every read is recorded.
    await record_audit(db, request, user, action="entity.freeze_packet", resource_type="entity", resource_id=str(entity_id))
    return packet
