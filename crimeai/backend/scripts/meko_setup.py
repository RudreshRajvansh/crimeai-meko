#!/usr/bin/env python3
"""
Set up Meko for this CrimeAI deployment. Every step is a live Meko call, logged to meko_calls.

  python scripts/meko_setup.py [--no-partners]

1. Datapacks: <prefix>-<agency> (this agency's private memory) and <prefix>-grid (shared between agencies),
   plus the private datapacks of the two partner agencies used in the demo (Gurugram, Noida).
2. SOP documents into the grid's knowledge base.
3. Partner history: Gurugram's and Noida's intake agents post their own (synthetic) cases to their private
   datapacks and minimised sightings to the grid, as their own CrimeAI deployments would.
4. Promoted exclusions on the grid are cached locally for link alerts.

Idempotent: existing datapacks are reused and cases already posted are skipped.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.session import create_engine
from app.meko import contract, service
from app.meko.client import MekoError, MekoRun, find_value, load_datapacks, open_run, rest, save_calls
from app.meko.models import MekoDatapack, MekoMemory
from app.nlp.privacy.redaction import redact

DATA = Path(__file__).parent.parent / "data" / "meko"
PARTNERS = ("GGM", "NOI")


def ok(msg: str) -> None:
    print(f"  [ok] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"  [!!] {msg}", flush=True)


async def ensure_datapacks(db, log: MekoRun, partners: bool) -> dict[str, str]:
    prefix, agency = settings.MEKO_DATAPACK_PREFIX, service.AGENCY
    wanted = {
        "agency": (f"{prefix}-{agency.lower()}", f"{contract.AGENCIES.get(agency, agency)}: private case memory of this CrimeAI deployment."),
        "grid": (f"{prefix}-grid", "Shared grid between agencies: identifier fingerprints, confirmed series, exclusions, SOPs."),
    }
    if partners:
        for code in PARTNERS:
            if code != agency:
                wanted[code.lower()] = (f"{prefix}-{code.lower()}", f"{contract.AGENCIES[code]}: private case memory (demo partner).")
    body, err = await rest(log, "GET", "/datapacks", agent="setup", label="list-datapacks", params={"limit": 100})
    items = (body or {}).get("data", {}) if isinstance(body, dict) else {}
    items = items.get("items", items) if isinstance(items, dict) else items
    existing = {(i.get("datapack_name") or i.get("name")): (i.get("datapack_id") or i.get("id"))
                for i in (items or []) if isinstance(i, dict)}
    if err:
        warn(f"could not list datapacks over REST ({err[:120]}); will try to create")
    out = {}
    for key, (name, description) in wanted.items():
        dp_id, how = existing.get(name), "existing"
        if not dp_id:
            body, err = await rest(log, "POST", "/datapacks", agent="setup", label="create-datapack",
                                   json_body={"name": name, "description": description})
            dp_id, how = find_value(body, ("datapack_id", "id")), "created"
            if err or not dp_id:
                warn(f"{name}: {err or 'no datapack id in response'}")
                continue
        out[key] = str(dp_id)
        await db.execute(insert(MekoDatapack).values(key=key, name=name, datapack_id=str(dp_id))
                         .on_conflict_do_update(index_elements=["key"], set_={"name": name, "datapack_id": str(dp_id)}))
        ok(f"{name} -> {dp_id} ({how})")
    return out


async def upload_sops(datapacks: dict[str, str]) -> list[dict]:
    pending = []
    async with open_run(datapacks, "setup") as run:
        for doc in sorted((DATA / "sop").glob("*.md")):
            content = doc.read_bytes()
            res, key = await run.kb_upload("setup", "grid", doc.name, content)
            if not res.ok:
                warn(f"{doc.name}: {(res.error or '')[:160]}")
                continue
            if res.first("already_uploaded"):
                ok(f"{doc.name} already in the knowledge base")
            else:
                ok(f"{doc.name} uploaded (sha256 {hashlib.sha256(content).hexdigest()[:12]}…)")
            if key:
                pending.append((doc.name, key))
        for _ in range(24):
            if not pending:
                break
            await asyncio.sleep(5)
            still = []
            for name, key in pending:
                status = str((await run.kb_status("setup", "grid", key)).first("state", "status") or "").lower()
                if status in ("completed", "complete", "indexed", "ready", "succeeded", "success"):
                    ok(f"{name} indexed")
                elif status in ("failed", "error", "abandoned", "oversized", "rejected"):
                    warn(f"{name} indexing {status}")
                else:
                    still.append((name, key))
            pending = still
        for name, _ in pending:
            warn(f"{name} still indexing; it becomes searchable shortly")
    return run.calls


async def post_partner_history(db, datapacks: dict[str, str]) -> list[dict]:
    cases = json.loads((DATA / "partner_cases.json").read_text(encoding="utf-8"))
    done = set((await db.execute(select(MekoMemory.case_ref).where(MekoMemory.kind == "sighting"))).scalars())
    todo = [c for c in cases if c["agency"].lower() in datapacks and contract.case_ref(c["agency"], c["case_number"]) not in done]
    if not todo:
        ok("partner history already on the grid")
        return []
    async with open_run(datapacks, "setup") as run:
        for c in todo:
            key, ref = c["agency"].lower(), contract.case_ref(c["agency"], c["case_number"])
            intake = f"{key}-intake"
            tokens = [i.token for i in contract.grid_identifiers(c["text"])]
            tags = contract.mo_tags(c["text"], c["crime_type"])
            summary = redact(c["text"]).text
            text = contract.agency_case_memory(ref, c["district"], c["date"], c["crime_type"], tags, tokens, summary)
            r1 = await run.memory_add(intake, key, text, {"kind": "case", "case_ref": ref})
            text2 = contract.sighting_memory(ref, c["district"], c["date"], c["crime_type"], tags, tokens)
            r2 = await run.memory_add(intake, "grid", text2, {"kind": "sighting", "case_ref": ref, "agency": c["agency"]})
            for res, dp, kind, submitted in ((r1, key, "case", text), (r2, "grid", "sighting", text2)):
                ids = [h.id for h in res.hits() if h.id] or ([str(res.first("memory_id", "id"))] if res.first("memory_id", "id") else [])
                for mid in ids:
                    db.add(MekoMemory(memory_id=mid, datapack=dp, agent=intake, kind=kind, case_ref=ref, text=submitted))
                if not res.ok:
                    warn(f"{ref} -> {dp}: {(res.error or '')[:200]}")
            if r1.ok and r2.ok:
                ok(f"{ref} ({contract.AGENCIES[c['agency']]}) posted: {len(tokens)} fingerprint(s), tags {', '.join(tags)}")
    return run.calls


async def main(args) -> int:
    print(f"Meko setup for {contract.AGENCIES.get(service.AGENCY, service.AGENCY)} ({settings.MEKO_MCP_URL})")
    if not settings.meko_enabled:
        warn("MEKO_API_KEY is empty. Put your key (mko_tkn_...) in backend/.env or the environment, then rerun.")
        return 1
    engine = create_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    log = MekoRun({}, "setup-" + uuid.uuid4().hex[:6])
    try:
        async with session_factory() as db:
            print("1. Datapacks")
            created = await ensure_datapacks(db, log, partners=not args.no_partners)
            await save_calls(db, log.calls)
            await db.commit()
            if "grid" not in created or "agency" not in created:
                warn("the agency and grid datapacks are required; fix the errors above and rerun")
                return 1
            log.calls.clear()

            print("2. SOP documents -> grid knowledge base")
            await save_calls(db, await upload_sops(await load_datapacks(db)))
            await db.commit()

            if not args.no_partners:
                print("3. Partner agencies post their history to the grid")
                calls = await post_partner_history(db, await load_datapacks(db))
                await save_calls(db, calls)
                await db.commit()

            print("4. Promoted exclusions -> local cache")
            ok(f"{await service.sync_exclusions(db)} exclusion(s) cached")
            await db.commit()
    except MekoError as e:
        warn(str(e))
        return 1
    finally:
        await engine.dispose()
    print("Done. Open the FIR page, paste a demo FIR (backend/data/meko/demo_firs.json) and compare Meko on and off.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-partners", action="store_true", help="skip the demo partner agencies")
    sys.exit(asyncio.run(main(parser.parse_args())))
