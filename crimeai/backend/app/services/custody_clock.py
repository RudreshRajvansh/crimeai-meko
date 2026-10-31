"""
Custody clock: statutory deadline for filing the final report (chargesheet).

Under BNSS s.187(3) (CrPC s.167(2) before 1 July 2024) an accused in custody
becomes entitled to default bail if investigation is not completed within
  * 90 days, for offences punishable with death, life imprisonment or
    imprisonment of not less than ten years
  * 60 days, for every other offence
"Not less than ten years" means a minimum term of ten years, not a maximum that
may extend to ten (Rajeev Chaudhary v. State (NCT of Delhi), 2001). The period
runs from the first remand, and the day of remand counts as day one
(Enforcement Directorate v. Kapil Wadhawan, 2023).

The track is decided from the cited sections' punishment, never from the crime
type: a stalking case classed "sexual_offense" is a 60-day case. Whenever the
track is uncertain the clock uses the earlier, 60-day deadline and says so,
because a late deadline lets default bail accrue unnoticed while an early one
only prompts a check. These rules come from secondary sources and must be
confirmed by a lawyer; the investigating officer remains responsible for the
legal computation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.nlp.legal.bns_crosswalk import IPC_TO_BNS, governing_code

# BNS sections punishable with death, life imprisonment, or a minimum of ten years.
NINETY_DAY_BNS_SECTIONS = {"103", "105", "64", "65", "66", "70", "71", "80", "140", "310"}
# Punishment reaches that level only in an aggravated form (e.g. attempt to murder with hurt), so the facts decide.
AMBIGUOUS_BNS_SECTIONS = {"109", "311"}
# Offence types that are often, but not always, on the 90-day track; used only to ask for verification.
SERIOUS_CRIME_TYPES = {"murder", "sexual_offense", "kidnapping"}

# Days remaining at which the case escalates, and the alert severity used.
ESCALATION_STEPS: tuple[tuple[int, str], ...] = ((2, "critical"), (7, "high"), (15, "medium"))


@dataclass(frozen=True, slots=True)
class Track:
    limit_days: int
    basis: str
    needs_verification: bool
    note: str | None = None


@dataclass(frozen=True, slots=True)
class CustodyDeadline:
    crime_id: str
    case_number: str | None
    crime_type: str
    district: str | None
    assigned_officer_id: str | None
    arrested_at: datetime
    limit_days: int
    deadline: datetime
    days_remaining: int
    status: str
    escalation: str | None
    clock_starts: str
    approximate: bool
    track_basis: str
    needs_verification: bool
    track_note: str | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["arrested_at"] = self.arrested_at.isoformat()
        data["deadline"] = self.deadline.isoformat()
        return data


def _bns_sections(legal_sections: list[str] | None, occurred_at: datetime | None) -> tuple[list[str], list[str]]:
    """BNS base sections for the cited ones, plus IPC sections the crosswalk cannot map."""
    bns, unmapped = [], []
    ipc = governing_code(occurred_at) == "IPC"
    for raw in legal_sections or []:
        base = raw.split("(")[0].strip().upper()
        if not base:
            continue
        if not ipc:
            bns.append(base)
        elif base in IPC_TO_BNS:
            bns.append(IPC_TO_BNS[base][0].split("(")[0])
        else:
            unmapped.append(base)
    return bns, unmapped


def track_for(crime_type: str, legal_sections: list[str] | None, occurred_at: datetime | None = None) -> Track:
    bns, unmapped = _bns_sections(legal_sections, occurred_at)
    if any(s in NINETY_DAY_BNS_SECTIONS for s in bns):
        return Track(90, "section", needs_verification=False)
    if any(s in AMBIGUOUS_BNS_SECTIONS for s in bns):
        return Track(60, "section", True, "Punishment depends on aggravating facts; confirm whether the 90-day track applies")
    if unmapped:
        return Track(60, "default", True, f"IPC {', '.join(unmapped)} not in the crosswalk; track not determined")
    if bns:
        return Track(60, "section", needs_verification=False)
    if crime_type in SERIOUS_CRIME_TYPES:
        return Track(60, "default", True, "No section cited for a serious offence; the 90-day track may apply")
    return Track(60, "default", True, "No section cited")


def limit_days_for(crime_type: str, legal_sections: list[str] | None, occurred_at: datetime | None = None) -> int:
    return track_for(crime_type, legal_sections, occurred_at).limit_days


def escalation_for(days_remaining: int) -> str | None:
    if days_remaining < 0:
        return "critical"
    for threshold, severity in ESCALATION_STEPS:
        if days_remaining <= threshold:
            return severity
    return None


def compute_deadline(crime: Any, now: datetime | None = None) -> CustodyDeadline:
    tz = ZoneInfo(settings.APP_TIMEZONE)
    now = now or datetime.now(UTC)
    track = track_for(crime.crime_type, crime.legal_sections, getattr(crime, "occurred_at", None))
    remanded_at = getattr(crime, "accused_first_remanded_at", None)
    started = remanded_at or crime.accused_arrested_at
    # Calendar days in the court's timezone, with the remand day as day one.
    first_day: date = started.astimezone(tz).date()
    last_day = first_day + timedelta(days=track.limit_days - 1)
    remaining = (last_day - now.astimezone(tz).date()).days
    return CustodyDeadline(
        crime_id=str(crime.id),
        case_number=crime.case_number,
        crime_type=crime.crime_type,
        district=crime.district,
        assigned_officer_id=str(crime.assigned_officer_id) if crime.assigned_officer_id else None,
        arrested_at=crime.accused_arrested_at,
        limit_days=track.limit_days,
        deadline=datetime.combine(last_day, time(23, 59, 59), tzinfo=tz),
        days_remaining=remaining,
        status="overdue" if remaining < 0 else "due_soon" if remaining <= 15 else "on_track",
        escalation=escalation_for(remaining),
        clock_starts="remand" if remanded_at else "arrest",
        approximate=remanded_at is None,
        track_basis=track.basis,
        needs_verification=track.needs_verification,
        track_note=track.note,
    )
