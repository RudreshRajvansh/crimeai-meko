"""Meko shared memory: recall before linking, share cases, officer decisions, and what Meko holds."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Analyst, Officer, Viewer
from app.core.config import settings
from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.meko import contract, service
from app.meko.client import MekoError, agent_id, load_datapacks
from app.meko.models import MekoCall, MekoDatapack
from app.models.crime import Crime
from app.services.audit_service import record_audit

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]
Datapack = Literal["agency", "grid"]


class RecallRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10000)


class SeriesDecision(BaseModel):
    own_ref: str | None = Field(None, max_length=80)
    refs: list[str] = Field(..., min_length=1, max_length=40)
    tokens: list[str] = Field(default_factory=list, max_length=20)
    mo_tags: list[str] = Field(default_factory=list, max_length=10)
    lead: str = Field("", max_length=120)
    note: str = Field("", max_length=300)


class AttachDecision(BaseModel):
    series_id: str = Field(..., max_length=20)
    own_ref: str = Field(..., max_length=80)
    tokens: list[str] = Field(default_factory=list, max_length=20)


class ExclusionDecision(BaseModel):
    token: str = Field(..., max_length=20)
    reason: str = Field("", max_length=200)


class MemoryEdit(BaseModel):
    text: str = Field(..., min_length=3, max_length=1500)


def _officer_label(user) -> str:
    return f"{user.role.value if hasattr(user.role, 'value') else user.role} officer, {contract.AGENCIES.get(service.AGENCY, service.AGENCY)}"


@router.get("/status", summary="Whether Meko is on, which datapacks this agency uses, and call counters")
async def meko_status(user: Viewer, db: DbDep) -> dict:
    datapacks = {d.key: {"name": d.name, "id": d.datapack_id}
                 for d in (await db.execute(select(MekoDatapack))).scalars()}
    rows = (await db.execute(
        select(MekoCall.category, MekoCall.ok, func.count()).group_by(MekoCall.category, MekoCall.ok)
    )).all()
    stats = {"write": 0, "recall": 0, "promote": 0, "delete": 0, "session": 0, "admin": 0, "errors": 0, "total": 0}
    for category, ok, n in rows:
        stats[category] = stats.get(category, 0) + n
        stats["total"] += n
        stats["errors"] += 0 if ok else n
    intake = service.INTAKE
    return {
        "enabled": settings.meko_enabled,
        "ready": settings.meko_enabled and all(k in datapacks for k in service.DATAPACK_KEYS),
        "agency": service.AGENCY,
        "agency_name": contract.AGENCIES.get(service.AGENCY, service.AGENCY),
        "mcp_url": settings.MEKO_MCP_URL,
        "datapacks": datapacks,
        "agents": {name: agent_id(name) for name in (intake, "linker", "briefer", "curator")},
        "stats": stats,
    }


@router.post("/recall", summary="Recall what other agencies and promoted officer decisions say about this FIR text")
@limiter.limit("30/minute")
async def meko_recall(request: Request, body: RecallRequest, user: Officer, db: DbDep) -> dict:
    result = await service.recall_for_text(db, body.text)
    analysis = result.get("analysis") or {}
    await record_audit(db, request, user, action="meko.recall", resource_type="fir_text",
                       metadata={"status": result["status"], "links": len(analysis.get("links", [])),
                                 "series": len(analysis.get("series", []))})
    return result


@router.post("/cases/{crime_id}/share", summary="Write a case to this agency's Meko memory and post its sighting to the grid")
async def meko_share(crime_id: uuid.UUID, request: Request, user: Officer, db: DbDep) -> dict:
    if await db.get(Crime, crime_id) is None:
        raise NotFoundError("Case not found")
    result = await service.share_case(db, crime_id)
    await record_audit(db, request, user, action="meko.share", resource_type="crime", resource_id=str(crime_id),
                       metadata={"status": result["status"]})
    return result


async def _decision(coro):
    try:
        return await coro
    except MekoError as exc:
        raise ExternalServiceError(str(exc)) from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/decisions/series", summary="Officer confirms a cross-agency link; the series is promoted to every agency")
async def confirm_series(body: SeriesDecision, request: Request, user: Officer, db: DbDep) -> dict:
    result = await _decision(service.confirm_series(
        db, own_ref=body.own_ref, refs=body.refs, tokens=body.tokens, tags=body.mo_tags, lead=body.lead,
        note=body.note, decided_by=_officer_label(user)))
    await record_audit(db, request, user, action="meko.series_confirmed", resource_type="meko_series",
                       resource_id=result["series_id"], metadata={"refs": body.refs, "promoted": result["promote"]["ok"]})
    return result


@router.post("/decisions/attach", summary="Officer attaches this case to a promoted series")
async def attach(body: AttachDecision, request: Request, user: Officer, db: DbDep) -> dict:
    result = await _decision(service.attach_to_series(
        db, series_id=body.series_id, own_ref=body.own_ref, tokens=body.tokens, decided_by=_officer_label(user)))
    await record_audit(db, request, user, action="meko.series_attached", resource_type="meko_series",
                       resource_id=body.series_id, metadata={"ref": body.own_ref})
    return result


@router.post("/decisions/exclusion", summary="Officer records an identifier is not a suspect's; promoted to every agency")
async def exclude(body: ExclusionDecision, request: Request, user: Officer, db: DbDep) -> dict:
    result = await _decision(service.exclude_identifier(db, token=body.token, reason=body.reason,
                                                        decided_by=_officer_label(user)))
    await record_audit(db, request, user, action="meko.identifier_excluded", resource_type="meko_identifier",
                       resource_id=body.token, metadata={"promoted": result["promote"]["ok"]})
    return result


@router.get("/memories/{datapack}", summary="What Meko holds in a datapack, exactly as memory_get_all returns it")
async def memories(datapack: Datapack, user: Analyst, db: DbDep, promoted: bool | None = None) -> dict:
    return await _decision(service.list_memories(db, datapack, promoted))


@router.patch("/memories/{datapack}/{memory_id}", summary="Correct a memory in Meko (redacted before it is sent)")
async def edit_memory(datapack: Datapack, memory_id: str, body: MemoryEdit, request: Request, user: Officer, db: DbDep) -> dict:
    result = await _decision(service.edit_memory(db, datapack, memory_id, body.text))
    await record_audit(db, request, user, action="meko.memory_corrected", resource_type="meko_memory",
                       resource_id=memory_id[:100], metadata={"datapack": datapack, "ok": result["ok"]})
    return result


@router.delete("/memories/{datapack}/{memory_id}", summary="Forget a memory in Meko")
async def forget_memory(datapack: Datapack, memory_id: str, request: Request, user: Officer, db: DbDep) -> dict:
    result = await _decision(service.forget_memory(db, datapack, memory_id))
    await record_audit(db, request, user, action="meko.memory_forgotten", resource_type="meko_memory",
                       resource_id=memory_id[:100], metadata={"datapack": datapack, "ok": result["ok"]})
    return result


@router.get("/calls", summary="Every Meko call this deployment made, newest first")
async def calls(user: Analyst, db: DbDep, limit: int = Query(100, ge=1, le=500), run_id: str | None = None) -> list[dict]:
    query = select(MekoCall).order_by(MekoCall.created_at.desc()).limit(limit)
    if run_id:
        query = select(MekoCall).where(MekoCall.run_id == run_id).order_by(MekoCall.created_at)
    return [{
        "id": str(c.id), "ts": c.created_at.isoformat(), "run_id": c.run_id, "agent": c.agent, "tool": c.tool,
        "category": c.category, "datapack": c.datapack, "transport": c.transport, "ok": c.ok,
        "latency_ms": c.latency_ms, "summary": c.summary, "args": c.args, "result": c.result,
    } for c in (await db.execute(query)).scalars()]


@router.get("/datapacks", summary="Datapack ids this deployment resolved at setup")
async def datapacks(user: Analyst, db: DbDep) -> dict:
    return await load_datapacks(db)
