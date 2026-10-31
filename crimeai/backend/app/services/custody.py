"""
Chain of custody for a case file.

Sealing hashes every document on the case (the FIR, statements, reports, memos, exactly as stored) and every
officer's review of a finding, builds a Merkle root over those hashes, and anchors the root on Solana in one Memo
transaction. Verifying recomputes the hashes from YugabyteDB, says which items changed, were added or were removed
since the seal, and reads the root back from the chain. Only hashes leave the deployment.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, NotFoundError
from app.integrations import solana
from app.models.crime import Crime
from app.models.custody import EvidenceSeal
from app.models.investigation import InvestigationFinding
from app.services import investigation_case

MEMO_PREFIX = "crimeai:seal:v1"


def leaf_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """Pairwise SHA-256 up to one root; an odd node is paired with itself."""
    level = [bytes.fromhex(h) for h in hashes]
    if not level:
        return hashlib.sha256(b"").hexdigest()
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def memo_for(case_ref: str, root: str, leaves: int) -> str:
    return f"{MEMO_PREFIX} case={case_ref} root={root} leaves={leaves}"


async def current_leaves(db: AsyncSession, crime: Crime) -> list[dict[str, Any]]:
    """Every document and every officer review on the case, each with the SHA-256 of its stored content."""
    leaves = []
    for row in await investigation_case.document_rows(db, crime):
        content = {"kind": "document", "id": row["id"], "doc_type": row["doc_type"], "title": row["title"],
                   "recorded_at": row["recorded_at"], "text": row["text"]}
        leaves.append({"kind": "document", "id": row["id"], "label": f"{row['type_label']}: {row['title']}",
                       "sha256": leaf_hash(content)})
    for f in (await db.execute(select(InvestigationFinding).where(InvestigationFinding.crime_id == crime.id))).scalars():
        content = {"kind": "review", "id": f.fingerprint, "status": f.status, "note": f.review_note,
                   "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None}
        leaves.append({"kind": "review", "id": f.fingerprint, "label": f"Review ({f.status}): {f.title}",
                       "sha256": leaf_hash(content)})
    return sorted(leaves, key=lambda leaf: (leaf["kind"], leaf["id"]))


def _seal_dict(s: EvidenceSeal) -> dict[str, Any]:
    return {"id": str(s.id), "created_at": s.created_at.isoformat() if s.created_at else None, "merkle_root": s.merkle_root,
            "leaves": len(s.leaves), "memo": s.memo, "cluster": s.cluster, "signature": s.signature, "slot": s.slot,
            "status": s.status, "error": s.error,
            "explorer_url": solana.explorer_url(s.signature) if s.signature else None}


def status() -> dict[str, Any]:
    out: dict[str, Any] = {"enabled": settings.solana_enabled, "cluster": settings.SOLANA_CLUSTER, "address": None}
    if out["enabled"]:
        out["address"] = str(solana.keypair().pubkey())
    return out


async def list_seals(db: AsyncSession, crime_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (await db.execute(select(EvidenceSeal).where(EvidenceSeal.crime_id == crime_id)
                             .order_by(EvidenceSeal.created_at.desc()))).scalars()
    return [_seal_dict(s) for s in rows]


async def seal(db: AsyncSession, crime_id: uuid.UUID, user_id: uuid.UUID | None) -> dict[str, Any]:
    crime = await db.get(Crime, crime_id)
    if crime is None:
        raise NotFoundError("Case not found")
    leaves = await current_leaves(db, crime)
    root = merkle_root([leaf["sha256"] for leaf in leaves])
    memo = memo_for(investigation_case.case_ref(crime), root, len(leaves))
    row = EvidenceSeal(crime_id=crime_id, merkle_root=root, leaves=leaves, memo=memo, cluster=settings.SOLANA_CLUSTER,
                       status="failed", sealed_by=user_id)
    try:
        sent = await solana.anchor(memo)
        row.signature, row.slot, row.status = sent["signature"], sent["slot"], sent["status"]
    except ExternalServiceError as exc:
        row.error = f"{exc}: {getattr(exc, 'detail', '') or ''}".strip(": ")[:1000]
    db.add(row)
    await db.flush()
    return _seal_dict(row)


async def verify(db: AsyncSession, crime_id: uuid.UUID, seal_id: uuid.UUID) -> dict[str, Any]:
    row = await db.get(EvidenceSeal, seal_id)
    crime = await db.get(Crime, crime_id)
    if row is None or crime is None or row.crime_id != crime_id:
        raise NotFoundError("Seal not found")
    now = {(leaf["kind"], leaf["id"]): leaf for leaf in await current_leaves(db, crime)}
    sealed = {(leaf["kind"], leaf["id"]): leaf for leaf in row.leaves}
    items = []
    for key in sorted(sealed.keys() | now.keys()):
        before, after = sealed.get(key), now.get(key)
        state = ("added" if before is None else "removed" if after is None
                 else "unchanged" if before["sha256"] == after["sha256"] else "changed")
        items.append({"kind": key[0], "id": key[1], "label": (after or before)["label"], "state": state})
    record_ok = merkle_root([leaf["sha256"] for leaf in row.leaves]) == row.merkle_root

    chain: dict[str, Any] = {"checked": False}
    if row.signature:
        try:
            onchain = await solana.memo_of(row.signature)
            chain = {"checked": True, "found": onchain is not None}
            if onchain:
                chain.update(onchain, matches=bool(onchain["memo"]) and f"root={row.merkle_root}" in onchain["memo"]
                             and not onchain["failed"])
                if chain["matches"] and row.status != "anchored":
                    row.status, row.slot = "anchored", onchain["slot"]
        except ExternalServiceError as exc:
            chain = {"checked": False, "error": str(exc)}
    changed = [i for i in items if i["state"] != "unchanged"]
    return {"seal": _seal_dict(row), "items": items, "record_ok": record_ok, "chain": chain,
            "intact": record_ok and not changed and bool(chain.get("matches"))}
