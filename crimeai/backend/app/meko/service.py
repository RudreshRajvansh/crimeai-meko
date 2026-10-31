"""
What CrimeAI's agents do with Meko.

  intake   (this agency)  recalls its own agency memory, writes the case there and posts a minimised sighting
                          (identifier fingerprints + method tags, no narrative) to the shared grid
  linker                  recalls the grid by identifier fingerprint and by method before anything is linked
  briefer                 searches the grid's SOP documents for the officer's next steps
  curator                 turns an officer's decision into grid knowledge and promotes it to every agency

People make the calls: agents only propose. Everything shown as context is exactly what Meko returned.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.meko import contract
from app.meko.client import MekoError, MekoRun, Result, context_buckets, load_datapacks, open_run, save_calls
from app.meko.models import MekoExclusion, MekoMemory
from app.models.crime import Crime
from app.models.fir import FIRReport
from app.nlp.privacy.redaction import redact

AGENCY = settings.MEKO_AGENCY_CODE
INTAKE = f"{AGENCY.lower()}-intake"
DATAPACK_KEYS = ("agency", "grid")


def enabled() -> bool:
    return settings.meko_enabled


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _query(tags: list[str], text: str) -> str:
    if tags:
        return "; ".join(contract.MO_TAGS[t] for t in tags) + f". MO tags: {', '.join(tags)}"
    return redact(text).text[:240]


class Recall:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.kb: list[dict] = []
        self._seen: set = set()

    def add(self, hits, dp: str, source: str, agent: str, call_id: str | None) -> int:
        n = 0
        for h in hits:
            key = (dp, h.id or h.text)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.items.append({"ref": f"M{len(self.items) + 1}", "id": h.id, "text": h.text, "score": h.score,
                               "datapack": dp, "source": source, "agent": agent, "call_id": call_id,
                               "parsed": contract.parse(h.text)})
            n += 1
        return n

    def add_kb(self, hits, call_id: str | None) -> int:
        n = 0
        for h in hits:
            if ("kb", h.text[:200]) in self._seen:
                continue
            self._seen.add(("kb", h.text[:200]))
            source = h.metadata.get("source") or h.metadata.get("filename") or h.metadata.get("file_name") or "SOP"
            self.kb.append({"ref": f"K{len(self.kb) + 1}", "id": h.id, "text": h.text, "score": h.score,
                            "source": source, "call_id": call_id})
            n += 1
        return n

    def public(self) -> list[dict]:
        return [{**{k: v for k, v in i.items() if k != "parsed"}, "parsed": i["parsed"].as_dict()} for i in self.items]


async def _recall(run: MekoRun, identifiers: list[contract.GridIdentifier], tags: list[str], text: str) -> tuple[Recall, list[dict]]:
    rc, steps = Recall(), []
    query = _query(tags, text)

    r = await run.memory_search(INTAKE, "agency", query, limit=5)
    n = rc.add(r.hits(), "agency", "memory", INTAKE, r.call_id)
    steps.append({"agent": INTAKE, "label": f"Recalled {contract.AGENCIES.get(AGENCY, AGENCY)}'s own memory: {n} item(s)",
                  "calls": [r.call_id], "errors": [r.error] if r.error else []})

    calls, errors, n = [], [], 0
    for ident in identifiers[:6]:
        r = await run.memory_search("linker", "grid", ident.token, limit=6)
        n += rc.add(r.hits(), "grid", "memory", "linker", r.call_id)
        calls.append(r.call_id)
        errors += [r.error] if r.error else []
    r = await run.context_search("linker", "grid", query, limit=8)
    calls.append(r.call_id)
    errors += [r.error] if r.error else []
    if r.ok:
        buckets = context_buckets(r.data)
        n += rc.add(buckets["memory"]["hits"] + buckets["conversation"]["hits"], "grid", "memory", "linker", r.call_id)
        rc.add_kb(buckets["knowledge_base"]["hits"], r.call_id)
    steps.append({"agent": "linker", "label": f"Recalled the shared grid by identifier fingerprint and by method: {n} item(s)",
                  "calls": calls, "errors": errors})

    r = await run.kb_search("briefer", "grid", f"Standard operating procedure: {query}", limit=3)
    k = rc.add_kb(r.hits("knowledge_base"), r.call_id)
    steps.append({"agent": "briefer", "label": f"Searched the grid's SOP documents: {k} passage(s)", "calls": [r.call_id],
                  "errors": [r.error] if r.error else []})
    return rc, steps


async def _cache_exclusions(db: AsyncSession, items: list[dict]) -> None:
    for it in items:
        if it["parsed"].kind != "exclusion":
            continue
        for token in it["parsed"].tokens:
            await db.execute(
                insert(MekoExclusion).values(token=token, memory_id=it["id"], text=it["text"][:2000])
                .on_conflict_do_update(index_elements=["token"], set_={"memory_id": it["id"], "text": it["text"][:2000]})
            )


async def excluded_tokens(db: AsyncSession) -> set[str]:
    if not enabled():
        return set()
    return set((await db.execute(select(MekoExclusion.token))).scalars().all())


def _status(datapacks: dict[str, str]) -> str | None:
    if not enabled():
        return "Meko is not configured on this server (MEKO_API_KEY is empty)."
    if any(k not in datapacks for k in DATAPACK_KEYS):
        return "Meko datapacks are not set up yet; run scripts/meko_setup.py."
    return None


async def recall_for_text(db: AsyncSession, text: str) -> dict[str, Any]:
    """The 'what do other agencies and our officers already know?' check, run before an FIR is linked."""
    identifiers = contract.grid_identifiers(text)
    tags = contract.mo_tags(text)
    base = {"agency": AGENCY, "agency_name": contract.AGENCIES.get(AGENCY, AGENCY),
            "identifiers": [i.as_dict() for i in identifiers], "mo_tags": tags}
    datapacks = await load_datapacks(db)
    if problem := _status(datapacks):
        return {**base, "status": "off", "error": problem, "calls": []}
    try:
        async with open_run(datapacks, INTAKE) as run:
            rc, steps = await _recall(run, identifiers, tags, text)
    except MekoError as e:
        calls = e.run.calls if e.run else []
        await save_calls(db, calls)
        return {**base, "status": "error", "error": str(e), "calls": calls}
    analysis = contract.analyse_recall(None, {i.token for i in identifiers}, tags, rc.items)
    await _cache_exclusions(db, rc.items)
    await save_calls(db, run.calls)
    return {**base, "status": "ok", "run_id": run.run_id, "steps": steps, "recalled": rc.public(), "kb": rc.kb,
            "analysis": analysis, "calls": run.calls}


async def _record(db: AsyncSession, res: Result, *, datapack: str, agent: str, kind: str, case_ref: str | None,
                  submitted: str) -> list[dict]:
    hits = res.hits()
    if hits:
        stored = [{"id": h.id, "text": h.text, "returned_by_meko": True} for h in hits if h.id]
    else:
        mid = res.first("memory_id", "id")
        stored = [{"id": str(mid) if mid else None, "text": submitted, "returned_by_meko": False}]
    for s in stored:
        s.update({"datapack": datapack, "agent": agent, "kind": kind, "ok": res.ok, "error": res.error, "call_id": res.call_id})
        if s["id"]:
            db.add(MekoMemory(memory_id=s["id"], datapack=datapack, agent=agent, kind=kind, case_ref=case_ref, text=s["text"]))
    return stored


async def share_case(db: AsyncSession, crime_id: uuid.UUID) -> dict[str, Any]:
    """Write a registered case to this agency's memory and post its sighting to the grid."""
    crime = await db.get(Crime, crime_id)
    if crime is None:
        return {"status": "error", "error": "case not found", "calls": []}
    raw = (await db.execute(
        select(FIRReport.raw_text).where(FIRReport.crime_id == crime_id).order_by(FIRReport.created_at.desc()).limit(1)
    )).scalar_one_or_none() or crime.description or ""
    datapacks = await load_datapacks(db)
    if problem := _status(datapacks):
        return {"status": "off", "error": problem, "calls": []}
    identifiers = contract.grid_identifiers(raw)
    tokens = [i.token for i in identifiers]
    tags = contract.mo_tags(raw, crime.crime_type)
    ref = contract.case_ref(AGENCY, crime.case_number or str(crime.id)[:8])
    date = (crime.occurred_at or datetime.now(UTC)).date().isoformat()
    summary = redact(raw).text
    stored: list[dict] = []
    try:
        async with open_run(datapacks, INTAKE) as run:
            conv = await run.conversation_create(INTAKE, "agency", f"Case {ref}", {"case_ref": ref})
            conv_id = conv.first("conversation_id", "id")
            if conv_id:
                await run.conversation_add_message(
                    INTAKE, "agency", str(conv_id),
                    user_input=f"FIR for case {ref} ({crime.district or 'district not recorded'}, {date}), redacted:\n{summary[:3000]}",
                    output=f"Registered as {crime.crime_type}; identifiers fingerprinted for the grid: {', '.join(tokens) or 'none'}.",
                    plan=["redact", "fingerprint identifiers", "store in agency memory", "post sighting to grid"],
                )
            text = contract.agency_case_memory(ref, crime.district, date, crime.crime_type, tags, tokens, summary)
            r = await run.memory_add(INTAKE, "agency", text, {"kind": "case", "case_ref": ref},
                                     str(conv_id) if conv_id else None)
            stored += await _record(db, r, datapack="agency", agent=INTAKE, kind="case", case_ref=ref, submitted=text)
            if tokens or contract.primary(tags):
                text = contract.sighting_memory(ref, crime.district, date, crime.crime_type, tags, tokens)
                r = await run.memory_add(INTAKE, "grid", text, {"kind": "sighting", "case_ref": ref, "agency": AGENCY})
                stored += await _record(db, r, datapack="grid", agent=INTAKE, kind="sighting", case_ref=ref, submitted=text)
    except MekoError as e:
        await save_calls(db, e.run.calls if e.run else [])
        return {"status": "error", "error": str(e), "case_ref": ref, "calls": e.run.calls if e.run else []}
    await save_calls(db, run.calls)
    return {"status": "ok", "case_ref": ref, "stored": stored, "calls": run.calls}


async def _write_and_promote(db: AsyncSession, run: MekoRun, text: str, kind: str, case_ref: str | None,
                             metadata: dict) -> dict:
    add = await run.memory_add("curator", "grid", text, metadata)
    stored = await _record(db, add, datapack="grid", agent="curator", kind=kind, case_ref=case_ref, submitted=text)
    ids = [s["id"] for s in stored if s["id"]]
    out: dict[str, Any] = {"memory_add": {"ok": add.ok, "error": add.error, "ids": ids, "stored": stored}}
    if not ids:
        out["promote"] = {"ok": False, "error": add.error or "Meko returned no memory id to promote"}
        return out
    prom = await run.memory_promote("curator", "grid", ids)
    out["promote"] = {"ok": prom.ok, "error": prom.error, "tool": prom.tool}
    if prom.ok:
        await db.execute(MekoMemory.__table__.update()
                         .where(MekoMemory.memory_id.in_(ids), MekoMemory.datapack == "grid").values(status="promoted"))
    return out


async def _decide(db: AsyncSession, text: str, kind: str, case_ref: str | None, metadata: dict) -> dict:
    datapacks = await load_datapacks(db)
    if problem := _status(datapacks):
        raise MekoError(problem)
    try:
        async with open_run(datapacks, "curator") as run:
            result = await _write_and_promote(db, run, text, kind, case_ref, metadata)
    except MekoError as e:
        await save_calls(db, e.run.calls if e.run else [])
        raise
    await save_calls(db, run.calls)
    if not result["memory_add"]["ok"]:
        raise MekoError(f"Meko did not store the decision: {result['memory_add']['error']}")
    return {**result, "text": text, "calls": run.calls}


def _clean(value: str) -> str:
    return redact(value or "").text.strip()


async def confirm_series(db: AsyncSession, *, own_ref: str | None, refs: list[str], tokens: list[str], tags: list[str],
                         lead: str, note: str, decided_by: str) -> dict:
    count = (await db.execute(select(func.count()).select_from(MekoMemory).where(MekoMemory.kind == "series"))).scalar_one()
    series_id = f"SR-{AGENCY}-{count + 1:02d}"
    members = sorted({*refs, *([own_ref] if own_ref else [])})
    text = contract.series_memory(series_id, [t for t in tags if t in contract.MO_TAGS and t not in contract.PAYMENT_TAGS],
                                  members, [t for t in tokens if contract.TOKEN_RE.fullmatch(t)],
                                  _clean(lead) or f"{contract.AGENCIES.get(AGENCY, AGENCY)} cyber cell", _clean(note),
                                  _clean(decided_by), _today())
    out = await _decide(db, text, "series", own_ref, {"kind": "series", "series_id": series_id})
    return {"series_id": series_id, **out}


async def attach_to_series(db: AsyncSession, *, series_id: str, own_ref: str, tokens: list[str], decided_by: str) -> dict:
    if not contract.SERIES_RE.fullmatch(series_id):
        raise ValueError("not a grid series id")
    text = contract.attach_memory(series_id, own_ref, [t for t in tokens if contract.TOKEN_RE.fullmatch(t)],
                                  _clean(decided_by), _today())
    return {"series_id": series_id, **await _decide(db, text, "attach", own_ref, {"kind": "attach", "series_id": series_id})}


async def exclude_identifier(db: AsyncSession, *, token: str, reason: str, decided_by: str) -> dict:
    if not contract.TOKEN_RE.fullmatch(token):
        raise ValueError("not an identifier fingerprint")
    text = contract.exclusion_memory(token, _clean(reason) or "officer judged it not to belong to a suspect",
                                     _clean(decided_by), _today())
    out = await _decide(db, text, "exclusion", None, {"kind": "exclusion", "token": token})
    ids = out["memory_add"]["ids"]
    await db.execute(insert(MekoExclusion).values(token=token, memory_id=ids[0] if ids else None, text=text)
                     .on_conflict_do_update(index_elements=["token"], set_={"text": text}))
    return {"token": token, **out}


def _writer(datapack: str, known: MekoMemory | None) -> str:
    if known is not None:
        return known.agent
    return INTAKE if datapack == "agency" else "curator"


async def list_memories(db: AsyncSession, datapack: str, promoted: bool | None = None) -> dict:
    datapacks = await load_datapacks(db)
    if problem := _status(datapacks):
        raise MekoError(problem)
    agent = INTAKE if datapack == "agency" else "curator"
    async with open_run(datapacks, agent) as run:
        res = await run.memory_get_all(agent, datapack, promoted)
    await save_calls(db, run.calls)
    ids = [h.id for h in res.hits() if h.id]
    known = {m.memory_id: m for m in (await db.execute(
        select(MekoMemory).where(MekoMemory.memory_id.in_(ids), MekoMemory.datapack == datapack))).scalars()} if ids else {}
    items = [{**h.as_dict(), "parsed": contract.parse(h.text).as_dict(),
              "writer": known[h.id].agent if h.id in known else None,
              "local_status": known[h.id].status if h.id in known else None} for h in res.hits()]
    return {"datapack": datapack, "ok": res.ok, "error": res.error, "total": res.first("total", "count"),
            "items": items, "calls": run.calls}


async def edit_memory(db: AsyncSession, datapack: str, memory_id: str, text: str) -> dict:
    clean = _clean(text)
    if not clean:
        raise ValueError("empty text")
    datapacks = await load_datapacks(db)
    known = (await db.execute(select(MekoMemory).where(MekoMemory.memory_id == memory_id,
                                                       MekoMemory.datapack == datapack))).scalars().first()
    async with open_run(datapacks, "curator") as run:
        res = await run.memory_update(_writer(datapack, known), datapack, memory_id, clean)
    await save_calls(db, run.calls)
    if res.ok and known is not None:
        known.text, known.status = clean, "edited"
    return {"ok": res.ok, "error": res.error, "text": clean, "calls": run.calls}


async def forget_memory(db: AsyncSession, datapack: str, memory_id: str) -> dict:
    datapacks = await load_datapacks(db)
    known = (await db.execute(select(MekoMemory).where(MekoMemory.memory_id == memory_id,
                                                       MekoMemory.datapack == datapack))).scalars().first()
    async with open_run(datapacks, "curator") as run:
        res = await run.memory_delete(_writer(datapack, known), datapack, memory_id)
    await save_calls(db, run.calls)
    if res.ok:
        if known is not None:
            known.status = "forgotten"
        await db.execute(MekoExclusion.__table__.delete().where(MekoExclusion.memory_id == memory_id))
    return {"ok": res.ok, "error": res.error, "calls": run.calls}


async def sync_exclusions(db: AsyncSession) -> int:
    """Pull every promoted exclusion from the grid into the local cache that link alerts consult."""
    datapacks = await load_datapacks(db)
    if _status(datapacks):
        return 0
    async with open_run(datapacks, "linker") as run:
        res = await run.memory_get_all("linker", "grid", True)
    await save_calls(db, run.calls)
    rc = Recall()
    rc.add(res.hits(), "grid", "memory", "linker", res.call_id)
    await _cache_exclusions(db, rc.items)
    return sum(1 for i in rc.items if i["parsed"].kind == "exclusion")
