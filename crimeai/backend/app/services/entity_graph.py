"""
Link analysis.

Cases are linked through the identifiers their narratives mention: vehicle
registration numbers, phone numbers, UPI IDs and bank accounts. The same
motorcycle in a vehicle-theft FIR and, a week later, a robbery FIR in another
district; the same UPI ID in five cyber-fraud complaints across four stations:
these links are exactly what siloed station records hide.

Privacy: phone numbers, UPI IDs and account numbers are stored only as a keyed
HMAC (ENTITY_HASH_KEY) plus a masked label, so two mentions link without the
identifier being stored. Vehicle numbers are kept as written; they are displayed
on the vehicle itself.

The graph is bipartite (cases and entities) plus crime-series nodes. Districts
and generic attributes (weapon types) are deliberately not nodes: they connect
everything to everything and drown the real links.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import Alert
from app.models.crime import Crime
from app.models.entity import Entity, EntityMention
from app.models.fir import FIRReport
from app.nlp.multilingual import analyse

LINKABLE_KINDS = ("vehicle", "phone", "upi", "account")
_MAX_NODES = 250


def _keyed(value: str) -> str:
    return hmac.new(settings.ENTITY_HASH_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()[:40]


def _mask(value: str, keep: int = 3) -> str:
    return value[:2] + "•" * max(len(value) - 2 - keep, 0) + value[-keep:]


# A bank account number only counts when a label names it; bare 9-18 digit runs are too often other numbers.
_ACCOUNT = re.compile(
    r"(?:\bA/?c\b|\bacc(?:oun)?t\b|खाता|হিসাব|கணக்கு)\s*(?:no\.?|number|संख्या|नं\.?|#)?\s*[:.\-]?\s*(\d{9,18})\b",
    re.I,
)


def accounts_in(text: str) -> list[str]:
    return list(dict.fromkeys(_ACCOUNT.findall(text or "")))


def account_identifier(number: str) -> tuple[str, str, str]:
    return ("account", _keyed(number), _mask(number, 4))


def identifiers_in(text: str) -> list[tuple[str, str, str]]:
    """(kind, key, label) for every linkable identifier in a narrative, in any language."""
    analysis = analyse(text or "")
    found = [("vehicle", plate, plate) for plate in analysis.vehicles]
    found += [("phone", _keyed(p), _mask(p)) for p in analysis.phones]
    for upi in analysis.upi_ids:
        handle, _, bank = upi.partition("@")
        found.append(("upi", _keyed(upi), f"{_mask(handle, 2)}@{bank}"))
    found += [account_identifier(a) for a in accounts_in(text)]
    return found


async def link_crime(db: AsyncSession, crime_id: uuid.UUID, text: str, fir_id: uuid.UUID | None = None,
                     occurred_at: datetime | None = None) -> list[uuid.UUID]:
    """Upsert the entities a narrative mentions and attach them to the case. Returns linked entity ids."""
    return await link_identifiers(db, crime_id, identifiers_in(text), fir_id, occurred_at)


async def link_identifiers(db: AsyncSession, crime_id: uuid.UUID, identifiers: list[tuple[str, str, str]],
                           fir_id: uuid.UUID | None = None, occurred_at: datetime | None = None,
                           source: str = "nlp") -> list[uuid.UUID]:
    """Attach (kind, key, label) identifiers to a case, from a narrative or a structured source such as NCRP."""
    linked: list[uuid.UUID] = []
    seen_at = occurred_at or datetime.now(UTC)
    for kind, key, label in dict.fromkeys(identifiers):
        stmt = (
            insert(Entity)
            .values(kind=kind, key=key, label=label, attributes={}, first_seen=seen_at, last_seen=seen_at)
            .on_conflict_do_update(
                constraint="uq_entities_kind_key",
                set_={"last_seen": func.greatest(Entity.last_seen, seen_at),
                      "first_seen": func.least(Entity.first_seen, seen_at)},
            )
            .returning(Entity.id)
        )
        entity_id = (await db.execute(stmt)).scalar_one()
        await db.execute(
            insert(EntityMention)
            .values(entity_id=entity_id, crime_id=crime_id, fir_id=fir_id, source=source)
            .on_conflict_do_nothing(constraint="uq_entity_mentions_entity_crime")
        )
        linked.append(entity_id)
    if linked:
        await _refresh_case_counts(db, linked)
    return linked


async def _refresh_case_counts(db: AsyncSession, entity_ids: list[uuid.UUID]) -> None:
    counts = (
        select(EntityMention.entity_id, func.count(func.distinct(EntityMention.crime_id)).label("n"))
        .where(EntityMention.entity_id.in_(entity_ids))
        .group_by(EntityMention.entity_id)
        .subquery()
    )
    rows = (await db.execute(select(counts.c.entity_id, counts.c.n))).all()
    for entity_id, n in rows:
        entity = await db.get(Entity, entity_id)
        if entity is not None:
            entity.case_count = n


async def link_alerts(db: AsyncSession, entity_ids: list[uuid.UUID]) -> list[Alert]:
    """
    One alert per identifier once it ties together enough separate cases. When more cases join later,
    the same alert is updated and marked unread again instead of stacking a new alert per case.
    """
    changed: list[Alert] = []
    for entity_id in set(entity_ids):
        entity = await db.get(Entity, entity_id)
        if entity is None or entity.case_count < settings.LINK_ALERT_MIN_CASES:
            continue
        key = f"link:{entity.id}"
        existing = (await db.execute(select(Alert).where(Alert.dedupe_key == key))).scalar_one_or_none()
        if existing is not None and existing.related_cluster_id == entity.case_count:
            continue
        districts = [d for d in (await db.execute(
            select(func.array_agg(func.distinct(Crime.district)))
            .join(EntityMention, EntityMention.crime_id == Crime.id)
            .where(EntityMention.entity_id == entity.id)
        )).scalar_one() or [] if d]
        noun = {"vehicle": "Vehicle", "phone": "Phone number", "upi": "UPI ID", "account": "Bank account"}[entity.kind]
        title = f"{noun} {entity.label} links {entity.case_count} cases"
        message = (
            f"{noun} {entity.label} appears in {entity.case_count} separate cases"
            f"{' across ' + ', '.join(sorted(districts)) if len(districts) > 1 else ''}. "
            "Open it in Link Analysis to review the connected cases together."
        )
        severity = "high" if entity.case_count >= 3 or len(districts) > 1 else "medium"
        if existing is None:
            existing = Alert(title=title, message=message, alert_type="pattern", severity=severity,
                             target_role="analyst", dedupe_key=key)
            db.add(existing)
        else:
            existing.title, existing.message, existing.severity = title, message, severity
            existing.is_read = False
        existing.related_cluster_id = entity.case_count
        changed.append(existing)
    await db.flush()
    return changed


def _crime_node(c: Any) -> dict[str, Any]:
    return {
        "id": f"crime:{c.id}",
        "type": "crime",
        "label": c.case_number or str(c.id)[:8],
        "crime_type": c.crime_type,
        "district": c.district,
        "severity": c.severity,
        "occurred_at": c.occurred_at.isoformat() if c.occurred_at else None,
        "series_id": c.series_id,
        "lat": c.latitude,
        "lng": c.longitude,
    }


def _entity_node(e: Entity) -> dict[str, Any]:
    return {
        "id": f"entity:{e.id}",
        "type": e.kind,
        "label": e.label,
        "case_count": e.case_count,
        "first_seen": e.first_seen.isoformat(),
        "last_seen": e.last_seen.isoformat(),
    }


async def _assemble(db: AsyncSession, crime_ids: set[uuid.UUID], entity_ids: set[uuid.UUID]) -> dict[str, Any]:
    crimes = (await db.execute(
        select(Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.severity, Crime.occurred_at,
               Crime.series_id, Crime.latitude, Crime.longitude).where(Crime.id.in_(crime_ids))
    )).all() if crime_ids else []
    entities = (await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars().all() if entity_ids else []
    mentions = (await db.execute(
        select(EntityMention.entity_id, EntityMention.crime_id)
        .where(EntityMention.entity_id.in_(entity_ids), EntityMention.crime_id.in_(crime_ids))
    )).all() if crime_ids and entity_ids else []

    nodes = [_crime_node(c) for c in crimes] + [_entity_node(e) for e in entities]
    links = [{"source": f"entity:{e}", "target": f"crime:{c}", "kind": "mentions"} for e, c in mentions]
    series: dict[str, list[str]] = {}
    for c in crimes:
        if c.series_id:
            series.setdefault(c.series_id, []).append(f"crime:{c.id}")
    for series_id, members in series.items():
        nodes.append({"id": f"series:{series_id}", "type": "series", "label": series_id, "size": len(members)})
        links += [{"source": f"series:{series_id}", "target": m, "kind": "member_of"} for m in members]
    return {
        "nodes": nodes,
        "links": links,
        "stats": {
            "cases": len(crimes),
            "entities": len(entities),
            "series": len(series),
            "districts": len({c.district for c in crimes if c.district}),
        },
    }


async def overview(db: AsyncSession, min_cases: int = 2, limit_entities: int = 60) -> dict[str, Any]:
    """Every identifier that ties two or more cases together, with those cases: the 'what is connected' view."""
    entities = (await db.execute(
        select(Entity.id).where(Entity.case_count >= min_cases).order_by(Entity.case_count.desc()).limit(limit_entities)
    )).scalars().all()
    crime_ids = set((await db.execute(
        select(EntityMention.crime_id).where(EntityMention.entity_id.in_(entities))
    )).scalars().all()) if entities else set()
    series_members = set((await db.execute(
        select(Crime.id).where(Crime.series_id.is_not(None), Crime.occurred_at >= datetime.now(UTC) - timedelta(days=120))
    )).scalars().all())
    graph = await _assemble(db, crime_ids | series_members, set(entities))
    counts = dict((await db.execute(select(Entity.kind, func.count(Entity.id)).group_by(Entity.kind))).all())
    graph["stats"]["entities_by_kind"] = counts
    graph["stats"]["linking_entities"] = len(entities)
    return graph


async def neighbourhood(db: AsyncSession, node: str, depth: int = 2) -> dict[str, Any]:
    """Breadth-first expansion from a case, entity or series node, capped to keep the canvas readable."""
    kind, _, raw = node.partition(":")
    crime_ids: set[uuid.UUID] = set()
    entity_ids: set[uuid.UUID] = set()
    if kind == "series":
        crime_ids = set((await db.execute(select(Crime.id).where(Crime.series_id == raw))).scalars().all())
        frontier = deque((f"crime:{c}", 1) for c in crime_ids)
    else:
        start = uuid.UUID(raw)
        (crime_ids if kind == "crime" else entity_ids).add(start)
        frontier = deque([(node, 0)])

    while frontier and len(crime_ids) + len(entity_ids) < _MAX_NODES:
        current, level = frontier.popleft()
        if level >= depth:
            continue
        current_kind, _, current_id = current.partition(":")
        if current_kind == "crime":
            neighbours = (await db.execute(
                select(EntityMention.entity_id).where(EntityMention.crime_id == uuid.UUID(current_id))
            )).scalars().all()
            for n in neighbours:
                if n not in entity_ids:
                    entity_ids.add(n)
                    frontier.append((f"entity:{n}", level + 1))
            series_id = (await db.execute(select(Crime.series_id).where(Crime.id == uuid.UUID(current_id)))).scalar_one_or_none()
            if series_id:
                for c in (await db.execute(select(Crime.id).where(Crime.series_id == series_id))).scalars().all():
                    if c not in crime_ids:
                        crime_ids.add(c)
                        frontier.append((f"crime:{c}", level + 1))
        else:
            neighbours = (await db.execute(
                select(EntityMention.crime_id).where(EntityMention.entity_id == uuid.UUID(current_id))
            )).scalars().all()
            for n in neighbours:
                if n not in crime_ids:
                    crime_ids.add(n)
                    frontier.append((f"crime:{n}", level + 1))
    return await _assemble(db, crime_ids, entity_ids)


async def search(db: AsyncSession, query: str, limit: int = 12) -> list[dict[str, Any]]:
    q = query.strip()
    if len(q) < 2:
        return []
    candidates = {q.upper().replace(" ", "").replace("-", "")}
    keyed = {_keyed(q.lower()), _keyed("".join(ch for ch in q if ch.isdigit())[-10:])}
    rows = (await db.execute(
        select(Entity).where(or_(
            Entity.key.in_(candidates | keyed), Entity.label.ilike(f"%{q}%"),
        )).order_by(Entity.case_count.desc()).limit(limit)
    )).scalars().all()
    return [_entity_node(e) for e in rows]


async def check_text(db: AsyncSession, text: str, cases_per_identifier: int = 12) -> dict[str, Any]:
    """
    Read-only: which identifiers in an unsaved narrative are already on record, and in which cases.
    Nothing is stored; this is the "have we seen this number before?" check run the moment an FIR is scanned.
    """
    analysis = analyse(text or "")
    matches: list[dict[str, Any]] = []
    for kind, key, label in dict.fromkeys(identifiers_in(text)):
        entity = (await db.execute(
            select(Entity).where(Entity.kind == kind, Entity.key == key)
        )).scalar_one_or_none()
        cases: list[dict[str, Any]] = []
        if entity is not None:
            rows = (await db.execute(
                select(Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.occurred_at,
                       FIRReport.language)
                .join(EntityMention, EntityMention.crime_id == Crime.id)
                .outerjoin(FIRReport, FIRReport.crime_id == Crime.id)
                .where(EntityMention.entity_id == entity.id)
                .order_by(Crime.occurred_at.desc())
                .limit(cases_per_identifier)
            )).all()
            cases = [{
                "id": str(r.id),
                "case_number": r.case_number,
                "crime_type": r.crime_type,
                "district": r.district,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                "language": r.language,
            } for r in rows]
        matches.append({
            "kind": kind,
            "label": label,
            "entity_id": str(entity.id) if entity is not None else None,
            "case_count": entity.case_count if entity is not None else 0,
            "districts": sorted({c["district"] for c in cases if c["district"]}),
            "cases": cases,
        })
    matches.sort(key=lambda m: m["case_count"], reverse=True)
    return {
        "language": analysis.language,
        "language_name": analysis.language_name,
        "identifiers": len(matches),
        "known": sum(1 for m in matches if m["case_count"] > 0),
        "matches": matches,
    }


async def entities_for_crime(db: AsyncSession, crime_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(Entity).join(EntityMention, EntityMention.entity_id == Entity.id).where(EntityMention.crime_id == crime_id)
    )).scalars().all()
    return [_entity_node(e) for e in rows]


async def case_map(db: AsyncSession, crime_id: uuid.UUID, similar: int = 8) -> dict[str, Any]:
    """
    One case and what it matches, for the map: cases sharing a phone, UPI ID, account or vehicle (with the
    shared identifiers), cases in the same series, and cases whose narrative reads alike (embedding distance).
    """
    from app.ml.similarity.crime_similarity import find_similar_crimes

    # Explicit columns: the embedding is deferred on the model, and a lazy load cannot run here.
    focus = (await db.execute(
        select(Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.severity, Crime.occurred_at,
               Crime.series_id, Crime.latitude, Crime.longitude, Crime.location_name, Crime.embedding)
        .where(Crime.id == crime_id)
    )).one_or_none()
    if focus is None:
        return {}
    shared: dict[uuid.UUID, list[str]] = {}
    for entity in (await db.execute(
        select(Entity).join(EntityMention, EntityMention.entity_id == Entity.id).where(EntityMention.crime_id == crime_id)
    )).scalars().all():
        for other in (await db.execute(
            select(EntityMention.crime_id).where(EntityMention.entity_id == entity.id, EntityMention.crime_id != crime_id)
        )).scalars().all():
            shared.setdefault(other, []).append(f"{entity.kind}: {entity.label}")
    series = set((await db.execute(
        select(Crime.id).where(Crime.series_id == focus.series_id, Crime.id != crime_id)
    )).scalars().all()) if focus.series_id else set()
    alike = await find_similar_crimes(db, list(focus.embedding), top_k=similar, min_similarity=0.55,
                                      exclude_id=crime_id) if focus.embedding is not None else []
    score = {uuid.UUID(a["id"]): a["similarity"] for a in alike}

    ids = set(shared) | series | set(score)
    rows = (await db.execute(
        select(Crime.id, Crime.case_number, Crime.crime_type, Crime.district, Crime.severity, Crime.occurred_at,
               Crime.latitude, Crime.longitude, Crime.series_id).where(Crime.id.in_(ids))
    )).all() if ids else []
    matches = sorted((
        {
            **{k: v for k, v in _crime_node(r).items() if k not in ("id", "type")},
            "id": str(r.id),
            "shared": shared.get(r.id, []),
            "same_series": r.id in series,
            "similarity": score.get(r.id),
            "reason": "identifier" if r.id in shared else "series" if r.id in series else "modus_operandi",
        } for r in rows
    ), key=lambda m: (m["reason"] != "identifier", m["reason"] != "series", -(m["similarity"] or 0)))
    return {
        "case": {**{k: v for k, v in _crime_node(focus).items() if k not in ("id", "type")}, "id": str(focus.id),
                 "location_name": focus.location_name},
        "matches": matches,
        "counts": {
            "identifier": sum(m["reason"] == "identifier" for m in matches),
            "series": sum(m["reason"] == "series" for m in matches),
            "modus_operandi": sum(m["reason"] == "modus_operandi" for m in matches),
        },
    }
