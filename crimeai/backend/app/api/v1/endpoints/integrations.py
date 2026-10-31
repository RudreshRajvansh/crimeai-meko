"""Connections to CCTNS, NCRP, e-Sakshya and the ICJS systems (see app/integrations)."""
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import Admin, Analyst, Officer
from app.api.v1.uploads import read_capped
from app.core.exceptions import NotFoundError, ValidationError
from app.db.redis import get_redis
from app.db.session import get_db
from app.integrations import esakshya
from app.integrations.importers import import_cctns, import_ncrp, parse_records
from app.integrations.registry import CONNECTORS
from app.models.crime import Crime
from app.realtime.broker import publish_alert
from app.services import entity_graph
from app.services.audit_service import record_audit
from app.services.dossier import build_dossier

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]
_MAX_IMPORT_BYTES = 20 * 1024 * 1024


@router.get("/", summary="Each external system: what flows in and out, and how far the connection has got")
async def list_connectors(user: Analyst) -> list[dict]:
    return [c.to_dict() for c in CONNECTORS]


async def _records(file: UploadFile) -> list[dict]:
    try:
        return parse_records(await read_capped(file, _MAX_IMPORT_BYTES), file.filename)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError(f"Could not read the file: {exc}") from exc


@router.post("/cctns/import", summary="Import a CCTNS FIR export (JSON or CSV); idempotent by FIR number")
async def cctns_import(request: Request, user: Admin, db: DbDep, file: Annotated[UploadFile, File()]) -> dict:
    report = await import_cctns(db, await _records(file), user.user_id)
    await record_audit(db, request, user, action="integration.cctns_import", resource_type="integration",
                       resource_id="cctns", metadata=report.to_dict())
    return report.to_dict()


@router.post("/ncrp/import", summary="Import NCRP / 1930 complaints (JSON or CSV); links mule identifiers at once")
async def ncrp_import(
    request: Request, user: Officer, db: DbDep, redis: Annotated[Redis, Depends(get_redis)],
    file: Annotated[UploadFile, File()],
) -> dict:
    report = await import_ncrp(db, await _records(file))
    alerts = await entity_graph.link_alerts(db, list(report.linked_entities))
    await record_audit(db, request, user, action="integration.ncrp_import", resource_type="integration",
                       resource_id="ncrp", metadata=report.to_dict())
    await db.commit()
    for alert in alerts:
        await publish_alert(redis, alert)
    return {**report.to_dict(), "link_alerts": len(alerts)}


@router.get("/cctns/enrichment/{crime_id}", summary="Analysis to write back to CCTNS as case notes (JSON)")
async def cctns_enrichment(crime_id: uuid.UUID, request: Request, user: Officer, db: DbDep) -> dict:
    dossier = await build_dossier(db, crime_id, user)
    case = dossier["case"]
    await record_audit(db, request, user, action="integration.cctns_enrichment", resource_type="crime",
                       resource_id=str(crime_id))
    return {
        "schema": "crimeai.cctns-enrichment.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "case_number": case.get("case_number"),
        "fir_number": (dossier.get("fir") or {}).get("fir_number"),
        "legal": dossier.get("legal"),
        "linked_identifiers": [{"kind": e["kind"], "label": e["label"], "case_count": e.get("case_count")}
                               for e in dossier.get("linked_entities", [])],
        "similar_cases": [{"case_number": s.get("case_number"), "similarity": s.get("similarity")}
                          for s in dossier.get("similar_cases", [])],
        "series_id": (dossier.get("series") or {}).get("series_id"),
        "custody_deadline": dossier.get("custody"),
        "evidence": dossier.get("evidence"),
        "note": "Machine-generated analysis for the investigating officer to review; not part of the FIR record.",
    }


class EvidenceLinkRequest(BaseModel):
    sid: str = Field(min_length=12, max_length=40)
    provision: str = Field(default="105", max_length=10)
    packet_hash: str | None = Field(default=None, max_length=128)
    captured_at: datetime | None = None
    note: str | None = Field(default=None, max_length=300)


@router.post("/esakshya/{crime_id}/links", summary="Link an e-Sakshya recording (SID) to a case", status_code=201)
async def add_evidence_link(crime_id: uuid.UUID, body: EvidenceLinkRequest, request: Request, user: Officer,
                            db: DbDep) -> dict:
    if await db.get(Crime, crime_id) is None:
        raise NotFoundError("Case not found")
    link = await esakshya.add_link(db, crime_id, user.user_id, body.sid, body.provision, body.packet_hash,
                                   body.captured_at, body.note)
    await record_audit(db, request, user, action="evidence.link", resource_type="crime", resource_id=str(crime_id),
                       metadata={"sid": link.sid, "provision": link.provision})
    await db.commit()
    await db.refresh(link)
    return esakshya.link_to_dict(link)
