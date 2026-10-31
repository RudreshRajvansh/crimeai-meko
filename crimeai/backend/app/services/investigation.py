"""
Investigation intelligence: a case's documents read together.

  Evidence agent   compares what each document says about the incident (time, date, vehicle number, amount)
                   and raises a contradiction when two documents disagree
  Timeline agent   puts every dated fact from the case record, the documents and e-Sakshya into one
                   source-linked chronology, and flags long stretches with no recorded step

Both are rule-based and explainable: every claim keeps the document it came from and the sentence it was read
in. Findings are leads for an officer to review (accept, reject, or send for further investigation), never
conclusions about anyone.
"""
from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from itertools import pairwise
from typing import Any

from app.models.investigation import DOCUMENT_TYPES
from app.nlp.multilingual import analyse, normalise_digits

GAP_DAYS = 7
TIME_TOLERANCE_MIN = 30

_SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n+")
_INCIDENT_CUES = (
    "incident", "occurred", "happened", "took place", "stolen", "stole", "snatch", "robbed", "robbery", "attacked",
    "assault", "called", "call from", "fled", "took the", "taken", "seen", "leaving", "left the", "visible", "paid",
    "transferred", "debited", "lost", "cheated", "घटना", "हुई", "हुआ", "चोरी", "छीन", "लूट", "कॉल", "वारदात",
    "भागे", "देखा", "कट गए", "भेजे", "गंवाए", "hua", "hui", "chori", "cheen", "call aaya", "bhaag", "dekha", "kat gaye",
)
# Documents whose first stated time is the incident time even without a cue word (a CCTV note's "21:04").
_FIRST_TIME_IS_INCIDENT = {"fir", "witness_statement", "cctv_note", "investigation_report"}
_MONEY_CUES = ("paid", "lost", "debited", "transferred", "cheated", "stolen", "worth", "loss", "कट", "भेजे", "गंवाए",
               "नुकसान", "bheje", "kat gaye", "gawaye")

_TIME_12 = re.compile(r"(?<![\d:])(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)(?![a-z])", re.I)
_TIME_24 = re.compile(r"(?<![\d:./-])([01]?\d|2[0-3])[:.]([0-5]\d)(?![.:/-]?\d)\s*(?:hrs|hours|h\b)?", re.I)
_TIME_BAJE = re.compile(
    r"(सुबह|दोपहर|शाम|रात|subah|dopahar|shaam|sham|raat|morning|afternoon|evening|night)?\s*"
    r"(?:के\s*|ke\s*)?(?:करीब\s*|लगभग\s*|kareeb\s*|lagbhag\s*|around\s*|about\s*)?(\d{1,2})\s*(?:बजे|baje|o'?clock)",
    re.I,
)
_LATE = ("शाम", "रात", "shaam", "sham", "raat", "evening", "night")
_NOON = ("दोपहर", "dopahar", "afternoon")

_MONTHS = {
    **{m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                    "september", "october", "november", "december"], 1)},
    **{m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)},
    "sept": 9,
    **{m: i for i, m in enumerate(["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर",
                                    "अक्टूबर", "नवंबर", "दिसंबर"], 1)},
    "फरवरी": 2, "सितम्बर": 9, "नवम्बर": 11, "दिसम्बर": 12,
}
_MONTH_ALT = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))
_DATE_NUM = re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.]((?:19|20)\d{2})(?!\d)")
_DATE_DMY = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALT})\.?,?\s*((?:19|20)\d{{2}})?", re.I)
_DATE_MDY = re.compile(rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?,?\s*((?:19|20)\d{{2}})?", re.I)


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    doc_type: str
    text: str
    recorded_at: datetime | None = None


@dataclass(frozen=True)
class Claim:
    doc_id: str
    doc_title: str
    doc_type: str
    subject: str
    value: str
    display: str
    quote: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text or "") if s.strip()]


def _is_incident(sentence: str) -> bool:
    low = sentence.lower()
    return any(cue in low for cue in _INCIDENT_CUES)


def _fmt_time(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return time(h, m).strftime("%I:%M %p").lstrip("0")


def times_in(sentence: str) -> list[int]:
    """Clock times in a sentence, as minutes after midnight, in the order they appear."""
    text = normalise_digits(sentence)
    found: list[tuple[int, int]] = []
    taken: list[tuple[int, int]] = []

    def free(span: tuple[int, int]) -> bool:
        return all(span[1] <= a or span[0] >= b for a, b in taken)

    for m in _TIME_12.finditer(text):
        h, mm, half = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower().replace(".", "").replace(" ", "")
        if 1 <= h <= 12 and mm < 60:
            h = (h % 12) + (12 if half.startswith("p") else 0)
            found.append((m.start(), h * 60 + mm))
            taken.append(m.span())
    for m in _TIME_BAJE.finditer(text):
        if not free(m.span()):
            continue
        period, h = (m.group(1) or "").lower(), int(m.group(2))
        if not 0 <= h <= 24:
            continue
        late = period in _LATE and h < 12 and not (period in ("रात", "raat", "night") and h <= 4)
        if late or (period in _NOON and h <= 5):
            h += 12
        found.append((m.start(), (h % 24) * 60))
        taken.append(m.span())
    for m in _TIME_24.finditer(text):
        if free(m.span()):
            found.append((m.start(), int(m.group(1)) * 60 + int(m.group(2))))
            taken.append(m.span())
    return [minutes for _, minutes in sorted(found)]


def dates_in(sentence: str, default_year: int) -> list[date]:
    text = normalise_digits(sentence)
    found: list[tuple[int, date]] = []
    for m in _DATE_NUM.finditer(text):
        d, mo, y = (int(g) for g in m.groups())
        with suppress(ValueError):
            found.append((m.start(), date(y, mo, d)))
    for m in _DATE_DMY.finditer(text):
        with suppress(ValueError, KeyError):
            found.append((m.start(), date(int(m.group(3) or default_year), _MONTHS[m.group(2).lower()], int(m.group(1)))))
    for m in _DATE_MDY.finditer(text):
        with suppress(ValueError, KeyError):
            found.append((m.start(), date(int(m.group(3) or default_year), _MONTHS[m.group(1).lower()], int(m.group(2)))))
    out: list[date] = []
    for _, d in sorted(found):
        if d not in out:
            out.append(d)
    return out


def _amounts_in(sentence: str) -> list[float]:
    return analyse(sentence).amounts


def claims_for(doc: Doc, default_year: int) -> list[Claim]:
    """What one document says about the incident: its time, date, amount, and every vehicle number."""
    sentences = _sentences(doc.text)
    incident = [s for s in sentences if _is_incident(s)]
    claims: list[Claim] = []

    def claim(subject: str, value: str, display: str, quote: str) -> None:
        claims.append(Claim(doc.id, doc.title, doc.doc_type, subject, value, display, quote[:240]))

    time_source = next(((s, t[0]) for s in incident if (t := times_in(s))), None)
    if time_source is None and doc.doc_type in _FIRST_TIME_IS_INCIDENT:
        time_source = next(((s, t[0]) for s in sentences if (t := times_in(s))), None)
    if time_source:
        claim("incident_time", str(time_source[1]), _fmt_time(time_source[1]), time_source[0])

    date_source = next(((s, d[0]) for s in incident if (d := dates_in(s, default_year))), None)
    if date_source:
        claim("incident_date", date_source[1].isoformat(), date_source[1].strftime("%d %b %Y"), date_source[0])

    money = next(((s, a[0]) for s in sentences if any(c in s.lower() for c in _MONEY_CUES) and (a := _amounts_in(s))), None)
    if money:
        claim("amount", f"{money[1]:.2f}", f"Rs {money[1]:,.0f}", money[0])

    for s in sentences:
        for plate in analyse(s).vehicles:
            if not any(c.subject == "vehicle" and c.value == plate for c in claims):
                claim("vehicle", plate, plate, s)
    return claims


def _osa_distance(a: str, b: str) -> int:
    """Edit distance counting a swap of two neighbouring characters as one edit (a common transcription slip)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _fingerprint(subject: str, claims: list[Claim]) -> str:
    key = subject + "|" + "|".join(sorted(f"{c.doc_id}:{c.value}" for c in claims))
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _duration(minutes: int) -> str:
    h, m = divmod(abs(minutes), 60)
    return " ".join(p for p in (f"{h} h" if h else "", f"{m} min" if m else "") if p) or "0 min"


_ACTIONS = {
    "incident_time": "Review the original statements and clarify which time is correct; check the CCTV clock for drift.",
    "incident_date": "Re-examine the documents and the complainant on the date; the custody and limitation clocks depend on it.",
    "amount": "Reconcile with the bank or UPI transaction reference before drafting a freeze request.",
    "vehicle": "Check the number against the RC and the vehicle itself; correct the record if it is a transcription error.",
}
_SUBJECT = {"incident_time": "Incident time", "incident_date": "Incident date", "amount": "Amount", "vehicle": "Vehicle number"}


def evidence_agent(docs: list[Doc], default_year: int) -> tuple[list[Claim], list[dict[str, Any]]]:
    """Every claim each document makes, and a contradiction wherever two documents disagree."""
    claims = [c for d in docs for c in claims_for(d, default_year)]
    findings: list[dict[str, Any]] = []
    for subject in ("incident_time", "incident_date", "amount"):
        group = [c for c in claims if c.subject == subject]
        if len({c.value for c in group}) < 2:
            continue
        if subject == "incident_time":
            values = sorted({int(c.value) for c in group})
            spread = values[-1] - values[0]
            if spread < TIME_TOLERANCE_MIN:
                continue
            difference = _duration(spread)
        elif subject == "incident_date":
            values_d = sorted({date.fromisoformat(c.value) for c in group})
            days = (values_d[-1] - values_d[0]).days
            difference = f"{days} day{'s' if days != 1 else ''}"
        else:
            values_f = sorted({float(c.value) for c in group})
            if values_f[-1] - values_f[0] < max(1.0, values_f[0] * 0.01):
                continue
            difference = f"Rs {values_f[-1] - values_f[0]:,.0f}"
        shown = " vs ".join(dict.fromkeys(c.display for c in group))
        findings.append(_finding("evidence", "contradiction", subject, f"{_SUBJECT[subject]} differs between documents: {shown}",
                                 group, difference))

    plates = [c for c in claims if c.subject == "vehicle"]
    for i, a in enumerate(plates):
        for b in plates[i + 1:]:
            if a.doc_id == b.doc_id or a.value == b.value or a.value[:2] != b.value[:2]:
                continue
            same_doc_has_both = any(c.doc_id == a.doc_id and c.value == b.value for c in plates)
            distance = _osa_distance(a.value, b.value)
            if distance <= 2 and not same_doc_has_both:
                swapped = distance == 1 and sorted(a.value) == sorted(b.value)
                findings.append(_finding(
                    "evidence", "contradiction", "vehicle", f"Vehicle number recorded differently: {a.value} vs {b.value}",
                    [a, b], "two neighbouring characters swapped" if swapped else f"{distance} character(s) differ"))
    return claims, findings


def _finding(agent: str, kind: str, subject: str, title: str, claims: list[Claim], difference: str) -> dict[str, Any]:
    return {
        "fingerprint": _fingerprint(subject, claims),
        "agent": agent,
        "kind": kind,
        "subject": subject,
        "title": title,
        "difference": difference,
        "claims": [asdict(c) for c in claims],
        "suggested_action": _ACTIONS[subject],
        "documents": sorted({c.doc_title for c in claims}),
    }


@dataclass(frozen=True)
class Event:
    at: str
    date_only: bool
    label: str
    kind: str
    source: str
    source_id: str | None = None
    quote: str | None = None


def _iso(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def timeline_agent(case: dict[str, Any], docs: list[Doc], evidence: list[dict[str, Any]],
                   default_year: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One chronology from the case record, every document and e-Sakshya; gaps of a week or more become findings."""
    events: list[Event] = []
    if case.get("occurred_at"):
        events.append(Event(_iso(case["occurred_at"]), False, "Incident, as registered in the case", "incident", "Case record"))
    for label, key in (("Accused arrested", "accused_arrested_at"), ("First remand", "accused_first_remanded_at"),
                       ("Charge sheet filed", "chargesheet_filed_at")):
        if case.get(key):
            events.append(Event(_iso(case[key]), False, label, "custody", "Case record"))
    for d in docs:
        type_label = DOCUMENT_TYPES.get(d.doc_type, d.doc_type)
        if d.recorded_at:
            events.append(Event(_iso(d.recorded_at), False, f"{type_label} recorded", "document", d.title, d.id))
        for s in _sentences(d.text):
            for day in dates_in(s, default_year):
                noun = type_label if type_label.isupper() else type_label.lower()
                events.append(Event(day.isoformat(), True, f"Date mentioned in the {noun}", "mention", d.title,
                                    d.id, s[:200]))
    for link in evidence:
        if link.get("captured_at"):
            events.append(Event(link["captured_at"], False, f"e-Sakshya recording (BNSS s.{link.get('provision', '105')})",
                                "evidence", f"e-Sakshya {link.get('sid', '')}".strip()))

    def key(e: Event) -> tuple[str, int]:
        return (e.at[:10], 1 if e.date_only else 0)

    ordered = sorted(events, key=key)
    gaps: list[dict[str, Any]] = []
    start = case.get("occurred_at")
    days = sorted({e.at[:10] for e in ordered if not start or e.at[:10] >= _iso(start)[:10]})
    for a, b in pairwise(days):
        span = (date.fromisoformat(b) - date.fromisoformat(a)).days
        if span >= GAP_DAYS:
            gaps.append({
                "fingerprint": hashlib.sha256(f"gap|{a}|{b}".encode()).hexdigest()[:32],
                "agent": "timeline",
                "kind": "gap",
                "subject": "gap",
                "title": f"No recorded step for {span} days ({date.fromisoformat(a):%d %b} to {date.fromisoformat(b):%d %b})",
                "difference": f"{span} days",
                "claims": [],
                "from": a,
                "to": b,
                "suggested_action": "Check whether steps in this period went unrecorded, or whether the investigation stalled.",
                "documents": [],
            })
    return [asdict(e) for e in ordered], gaps


def default_year(case: dict[str, Any]) -> int:
    occurred = case.get("occurred_at")
    return occurred.year if isinstance(occurred, datetime) else datetime.now(UTC).year


def investigate(case: dict[str, Any], docs: list[Doc], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    year = default_year(case)
    claims, contradictions = evidence_agent(docs, year)
    events, gaps = timeline_agent(case, docs, evidence, year)
    return {"claims": [asdict(c) for c in claims], "findings": contradictions + gaps, "timeline": events,
            "gap_days": GAP_DAYS, "time_tolerance_min": TIME_TOLERANCE_MIN}
