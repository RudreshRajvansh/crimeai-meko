"""Case dossier: everything known about one case, assembled for a single screen."""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser
from app.core.exceptions import NotFoundError
from app.core.security import UserRole
from app.integrations import esakshya
from app.ml import registry
from app.ml.prediction.risk_scorer import CRIME_DANGER_WEIGHTS
from app.ml.similarity.crime_similarity import find_similar_crimes
from app.models.crime import Crime
from app.models.fir import FIRReport
from app.nlp.legal.bns_crosswalk import analyse_sections
from app.nlp.multilingual import analyse, normalise_for_legal
from app.repositories.crime_repository import CrimeRepository
from app.schemas.crime import CrimeResponse
from app.services import entity_graph
from app.services.custody_clock import compute_deadline


async def build_dossier(db: AsyncSession, crime_id: uuid.UUID, viewer: CurrentUser) -> dict[str, Any]:
    crime = await db.get(Crime, crime_id)
    if crime is None:
        raise NotFoundError("Case not found")

    fir = (await db.execute(select(FIRReport).where(FIRReport.crime_id == crime_id).limit(1))).scalar_one_or_none()
    officer = viewer.role in (UserRole.POLICE, UserRole.ADMIN)
    narrative = (fir.raw_text if officer else (fir.redacted_text or "")) if fir else (crime.description or "")
    language = analyse(narrative)
    legal = analyse_sections(normalise_for_legal(narrative), crime.occurred_at) if narrative else None

    embedding = (await db.execute(select(Crime.embedding).where(Crime.id == crime_id))).scalar_one_or_none()
    similar = []
    if embedding is not None:
        similar = await find_similar_crimes(db, list(embedding), top_k=6, min_similarity=0.0, exclude_id=crime_id)

    evidence = await esakshya.list_links(db, crime_id)

    series = None
    if crime.series_id:
        artifact = await registry.latest(db, registry.CRIME_SERIES)
        series = next((s for s in (artifact.as_json() if artifact else []) if s["series_id"] == crime.series_id), None)

    nearby = await CrimeRepository(db).find_within_radius(crime.latitude, crime.longitude, 1.0, limit=200)
    window = [c for c in nearby if c.id != crime.id and abs(c.occurred_at - crime.occurred_at) <= timedelta(days=30)]
    same_type = sum(1 for c in window if c.crime_type == crime.crime_type)

    district_rank = None
    if crime.district:
        rows = (await db.execute(
            select(Crime.district, func.count(Crime.id)).where(Crime.crime_type == crime.crime_type)
            .group_by(Crime.district).order_by(func.count(Crime.id).desc())
        )).all()
        district_rank = next((i + 1 for i, (d, _) in enumerate(rows) if d == crime.district), None)

    return {
        "case": CrimeResponse.model_validate(crime).model_dump(mode="json"),
        "fir": None if fir is None else {
            "id": str(fir.id),
            "fir_number": fir.fir_number,
            "nlp_status": fir.nlp_status,
            "file_sha256": fir.file_sha256,
            "entities": fir.extracted_entities,
        },
        "narrative": {
            "text": narrative,
            "redacted": bool(fir) and not officer,
            "language": {"code": language.language, "name": language.language_name, "script": language.script,
                         "confidence": language.confidence},
            "highlights": [asdict(h) for h in language.highlights],
        },
        "legal": legal,
        "linked_entities": await entity_graph.entities_for_crime(db, crime_id),
        "similar_cases": similar,
        "series": series,
        "custody": compute_deadline(crime).to_dict() if crime.accused_arrested_at and not crime.chargesheet_filed_at else None,
        "evidence": {
            "links": [esakshya.link_to_dict(link) for link in evidence],
            "s105_gap": esakshya.s105_gap(narrative or crime.description, evidence),
        },
        "context": {
            "within_1km_30d": len(window),
            "same_type_within_1km_30d": same_type,
            "district_rank_for_type": district_rank,
            "harm_weight": CRIME_DANGER_WEIGHTS.get(crime.crime_type),
        },
    }
