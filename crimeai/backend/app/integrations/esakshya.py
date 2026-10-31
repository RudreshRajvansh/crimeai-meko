"""
e-Sakshya references and the BNSS s.105 check.

BNSS s.105 requires searches and seizures to be recorded by audio-video means;
states route these recordings through the e-Sakshya app, which issues a session
id (SID) and a hash per packet, and their rules require the SID to be linked to
the CCTNS FIR. Courts have doubted recoveries that were not videographed. This
module stores only the reference, and flags cases whose narrative records a
seizure or recovery with no linked s.105 recording, so the gap is caught while
it can still be explained in the case diary, not at trial.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, ValidationError
from app.models.evidence_link import EvidenceLink

PROVISIONS = {
    "105": "Search and seizure",
    "173": "Information in cognizable cases (e-FIR / statement)",
    "176": "Crime scene (forensic team visit)",
    "180": "Examination of witnesses",
    "185": "Search by police officer during investigation",
    "497": "Custody and disposal of property",
}
# State rules describe a 16-digit SID; accept 12-32 digits so a format change does not block entry.
_SID = re.compile(r"^\d{12,32}$")
_HASH = re.compile(r"^[0-9a-fA-F]{32,128}$")
# Words that record a seizure or recovery, in English, Hindi, Marathi, Bengali, Tamil and Telugu FIRs.
_SEIZURE = re.compile(
    r"seiz|recover|confiscat|panchnama|जब्त|बरामद|ज़ब्त|जप्त|উদ্ধার|জব্দ|பறிமுதல்|மீட்|స్వాధీన",
    re.I,
)


def link_to_dict(link: EvidenceLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "sid": link.sid,
        "packet_hash": link.packet_hash,
        "provision": link.provision,
        "provision_label": PROVISIONS.get(link.provision, link.provision),
        "captured_at": link.captured_at.isoformat() if link.captured_at else None,
        "note": link.note,
        "linked_at": link.created_at.isoformat() if link.created_at else None,
    }


async def list_links(db: AsyncSession, crime_id: uuid.UUID) -> list[EvidenceLink]:
    rows = await db.execute(select(EvidenceLink).where(EvidenceLink.crime_id == crime_id).order_by(EvidenceLink.created_at))
    return list(rows.scalars().all())


async def add_link(db: AsyncSession, crime_id: uuid.UUID, user_id: uuid.UUID, sid: str, provision: str,
                   packet_hash: str | None = None, captured_at: Any = None, note: str | None = None) -> EvidenceLink:
    sid = re.sub(r"[\s-]", "", sid)
    if not _SID.fullmatch(sid):
        raise ValidationError("SID must be the numeric session id shown in the e-Sakshya app")
    if provision not in PROVISIONS:
        raise ValidationError(f"Provision must be one of BNSS s.{', s.'.join(PROVISIONS)}")
    if packet_hash and not _HASH.fullmatch(packet_hash):
        raise ValidationError("Packet hash must be the hexadecimal hash shown for the packet")
    if any(link.sid == sid for link in await list_links(db, crime_id)):
        raise AlreadyExistsError("This recording is already linked to the case")
    link = EvidenceLink(crime_id=crime_id, sid=sid, provision=provision, packet_hash=packet_hash,
                        captured_at=captured_at, note=(note or None), linked_by=user_id)
    db.add(link)
    await db.flush()
    return link


def s105_gap(narrative: str | None, links: list[EvidenceLink]) -> str | None:
    """A warning when the narrative records a seizure or recovery but no s.105 recording is linked."""
    if not narrative or not _SEIZURE.search(narrative):
        return None
    if any(link.provision == "105" for link in links):
        return None
    return ("The case records a seizure or recovery but no BNSS s.105 audio-video recording (e-Sakshya SID) "
            "is linked. Link the SID, or note in the case diary why it was not recorded.")
