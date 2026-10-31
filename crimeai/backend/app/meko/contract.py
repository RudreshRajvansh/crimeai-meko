"""
The memory contract: how facts are phrased when written to Meko, and how recalled text is read back.

Meko's memory_add runs model-based fact extraction, so stored text may be reworded or merged. Everything the
linker relies on is carried as tokens that survive rewording and is parsed from whatever text Meko returns:

  identifier fingerprints   UPI-7F3A9C21D0, PH-..., AC-..., VH-...   (HMAC with the shared MEKO_GRID_KEY)
  case references           DLP:DL-2026-1A2B3C4D, GGM:GGM-2026-0412  (agency code : case number)
  grid series ids           SR-DLP-01
  method tags               courier-customs, kyc-otp, ...
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.nlp.multilingual import analyse

KIND_PREFIX = {"phone": "PH", "upi": "UPI", "account": "AC", "vehicle": "VH"}
KIND_NOUN = {"phone": "Phone", "upi": "UPI ID", "account": "Bank account", "vehicle": "Vehicle"}
PREFIX_KIND = {v: k for k, v in KIND_PREFIX.items()}

AGENCIES = {
    "DLP": "Delhi Police",
    "GGM": "Gurugram Police",
    "NOI": "Noida Police",
}

MO_TAGS = {
    "courier-customs": "Fake courier or customs fee demand",
    "kyc-otp": "Fake bank KYC update or OTP request",
    "digital-arrest": "Fake police or agency video call threat",
    "task-job": "Paid online task or part-time job scam",
    "investment": "Fake trading or investment scheme",
    "loan-app": "Instant loan app harassment",
    "sim-swap": "SIM swap or eSIM takeover",
    "vehicle-lifting": "Vehicle stolen from parking",
    "upi": "Money paid over UPI",
    "bank-transfer": "Money moved by bank transfer",
    "screen-share": "Victim made to install a screen-sharing app",
}
PAYMENT_TAGS = {"upi", "bank-transfer", "screen-share"}
TAG_KEYWORDS = {
    "courier-customs": ("courier", "parcel", "customs", "fedex", "dhl", "पार्सल", "कूरियर", "कस्टम"),
    "kyc-otp": ("kyc", "otp", "account block", "card block", "account will be blocked", "ओटीपी", "केवाईसी"),
    "digital-arrest": ("digital arrest", "cbi", "narcotics", "arrest warrant", "video call by police"),
    "task-job": ("part-time", "part time", "like videos", "rating hotels", "rate hotels", "work from home", "prepaid task"),
    "investment": ("trading", "stock tips", "crypto", "ipo allotment", "guaranteed returns"),
    "loan-app": ("loan app", "instant loan", "morphed"),
    "sim-swap": ("sim swap", "esim", "duplicate sim", "sim stopped working"),
    "vehicle-lifting": ("motorcycle", "scooty", "scooter", "two-wheeler", "मोटरसाइकिल", "स्कूटी", "car was stolen"),
    "upi": ("upi", "gpay", "google pay", "phonepe", "paytm", "bhim"),
    "bank-transfer": ("neft", "imps", "rtgs", "bank transfer", "a/c"),
    "screen-share": ("anydesk", "teamviewer", "screen share", "quicksupport"),
}

TOKEN_RE = re.compile(r"\b(?:PH|UPI|AC|VH)-[0-9A-F]{10}\b")
CASE_RE = re.compile(r"\b([A-Z]{2,5}):([A-Z0-9][A-Za-z0-9/_-]{2,40}[A-Za-z0-9])")
SERIES_RE = re.compile(r"\bSR-[A-Z]{2,5}-\d{2,3}\b")
TAG_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(MO_TAGS, key=len, reverse=True)) + r")\b")
LEAD_RE = re.compile(r"Lead:\s*([^.]+)\.")
NOTE_RE = re.compile(r"Officer note:\s*\"([^\"]+)\"")
_ACCOUNT = re.compile(
    r"(?:\bA/?c\b|\bacc(?:oun)?t\b|खाता|হিসাব|கணக்கு)\s*(?:no\.?|number|संख्या|नं\.?|#)?\s*[:.\-]?\s*(\d{9,18})\b", re.I
)
_TOLLFREE = re.compile(r"(?<!\d)1[89]00[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)")


def fingerprint(kind: str, value: str) -> str:
    """Keyed fingerprint every agency computes identically from the same raw identifier, with the shared grid key."""
    digest = hmac.new(settings.MEKO_GRID_KEY.encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()
    return f"{KIND_PREFIX[kind]}-{digest[:10].upper()}"


@dataclass(frozen=True)
class GridIdentifier:
    kind: str
    token: str
    label: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "noun": KIND_NOUN[self.kind], "token": self.token, "label": self.label}


def _mask(value: str, keep: int = 3) -> str:
    return value[:2] + "•" * max(len(value) - 2 - keep, 0) + value[-keep:]


def grid_identifiers(text: str) -> list[GridIdentifier]:
    """Every linkable identifier in a narrative, as a grid fingerprint plus the masked label CrimeAI shows."""
    analysis = analyse(text or "")
    found: dict[str, GridIdentifier] = {}

    def add(kind: str, raw: str, label: str) -> None:
        token = fingerprint(kind, raw)
        found.setdefault(token, GridIdentifier(kind, token, label))

    for plate in analysis.vehicles:
        add("vehicle", plate.upper().replace(" ", "").replace("-", ""), plate)
    for phone in analysis.phones:
        add("phone", phone, _mask(phone))
    for tollfree in _TOLLFREE.findall(text or ""):
        digits = re.sub(r"\D", "", tollfree)
        add("phone", digits, _mask(digits))
    for upi in analysis.upi_ids:
        handle, _, bank = upi.lower().partition("@")
        add("upi", upi.lower(), f"{_mask(handle, 2)}@{bank}")
    for account in dict.fromkeys(_ACCOUNT.findall(text or "")):
        add("account", account, _mask(account, 4))
    return list(found.values())


def mo_tags(text: str, crime_type: str | None = None) -> list[str]:
    low = (text or "").lower()
    tags = [t for t, words in TAG_KEYWORDS.items() if any(w in low for w in words)]
    if crime_type == "vehicle_theft" and "vehicle-lifting" not in tags:
        tags.insert(0, "vehicle-lifting")
    return tags[:5]


def primary(tags) -> set[str]:
    return set(tags) - PAYMENT_TAGS


def case_ref(agency: str, case_number: str) -> str:
    return f"{agency}:{case_number}"


def _ids(items) -> str:
    return ", ".join(sorted(items))


def agency_case_memory(ref: str, district: str | None, date: str, crime_type: str, tags, tokens, summary: str) -> str:
    agency = AGENCIES.get(ref.split(":", 1)[0], ref.split(":", 1)[0])
    where = f" ({district})" if district else ""
    idents = f" Identifiers: {_ids(tokens)}." if tokens else ""
    return (f"Case {ref} was registered by {agency}{where} on {date}: {crime_type.replace('_', ' ')}, "
            f"MO tags {', '.join(tags) or 'none'}.{idents} Summary: {summary[:400]}")


def sighting_memory(ref: str, district: str | None, date: str, crime_type: str, tags, tokens) -> str:
    agency = AGENCIES.get(ref.split(":", 1)[0], ref.split(":", 1)[0])
    where = f", {district}" if district else ""
    idents = f"identifiers {_ids(tokens)}" if tokens else "no recorded identifiers"
    return (f"Sighting: case {ref} ({agency}{where}, {date}) involved {idents}. "
            f"Crime type {crime_type}. MO tags: {', '.join(tags) or 'none'}.")


def series_memory(series_id: str, tags, refs, tokens, lead: str, note: str, decided_by: str, date: str) -> str:
    note_part = f' Officer note: "{note}".' if note else ""
    return (f"Confirmed series {series_id} (MO tags {', '.join(tags) or 'none'}): cases {_ids(refs)} are one series, "
            f"linked on {_ids(tokens) or 'method'}. Lead: {lead}.{note_part} Confirmed by {decided_by} on {date}. "
            f"Attach new cases that share these identifiers or MO tags to {series_id}.")


def attach_memory(series_id: str, ref: str, tokens, decided_by: str, date: str) -> str:
    via = f" via {_ids(tokens)}" if tokens else " on MO match"
    return f"Case {ref} was attached to confirmed series {series_id}{via}. Confirmed by {decided_by} on {date}."


def approved_finding_memory(ref: str, title: str, difference: str, action: str, tokens, decided_by: str,
                            date: str) -> str:
    idents = f" Identifiers: {_ids(tokens)}." if tokens else ""
    return (f"Approved finding on case {ref}: {title} (difference: {difference}). Next step: {action}{idents} "
            f"Accepted by {decided_by} on {date}.")


def exclusion_memory(token: str, reason: str, decided_by: str, date: str) -> str:
    return (f"Exclusion: identifier {token} is not a suspect identifier ({reason}). "
            f"Do not link cases on {token}. Decided by {decided_by} on {date}.")


@dataclass
class Parsed:
    kind: str
    tokens: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)
    series_ids: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    lead: str = ""
    note: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "tokens": sorted(self.tokens), "refs": sorted(self.refs),
                "series_ids": sorted(self.series_ids), "tags": sorted(self.tags), "lead": self.lead, "note": self.note}


def parse(text: str) -> Parsed:
    low = text.lower()
    p = Parsed(
        kind="other",
        tokens=set(TOKEN_RE.findall(text)),
        refs={f"{a}:{n}" for a, n in CASE_RE.findall(text) if a in AGENCIES or a.isupper()},
        series_ids=set(SERIES_RE.findall(text)),
        tags=set(TAG_RE.findall(low)),
    )
    if m := LEAD_RE.search(text):
        p.lead = m.group(1).strip()
    if m := NOTE_RE.search(text):
        p.note = m.group(1).strip()
    if "approved finding" in low:
        p.kind = "approved"
    elif "exclusion" in low or "not a suspect" in low or "do not link" in low:
        p.kind = "exclusion"
    elif p.series_ids:
        p.kind = "series"
    elif "sighting" in low or (p.tokens and p.refs and "registered by" not in low):
        p.kind = "sighting"
    elif p.refs:
        p.kind = "case"
    return p


def analyse_recall(own_ref: str | None, tokens: set[str], tags, items: list[dict]) -> dict:
    """
    Links over recalled memories only. items: [{ref, id, text, score, datapack, parsed: Parsed}].
    Returns identifier links to other agencies' cases, matched series, method-only matches and exclusions.
    """
    own = {own_ref} if own_ref else set()
    main = primary(tags)
    exclusions: dict[str, dict] = {}
    for it in items:
        if it["parsed"].kind == "exclusion":
            for t in it["parsed"].tokens:
                exclusions.setdefault(t, it)
    strong: dict[str, dict] = {}
    similar: dict[str, dict] = {}
    series: dict[str, dict] = {}
    for it in items:
        p = it["parsed"]
        if p.kind == "exclusion":
            continue
        shared = (p.tokens & tokens) - exclusions.keys()
        others = p.refs - own
        overlap = primary(p.tags) & main
        if p.kind == "series":
            for sid in p.series_ids:
                member = bool(own & p.refs)
                if not (shared or overlap or member):
                    continue
                s = series.setdefault(sid, {"series_id": sid, "tokens": set(), "mo_tags": set(), "refs": set(),
                                            "basis": set(), "evidence": [], "lead": "", "note": "", "member": False})
                s["tokens"] |= shared
                s["mo_tags"] |= overlap
                s["refs"] |= others
                s["basis"].add("identifier" if shared else "method")
                s["evidence"].append(it["ref"])
                s["lead"] = s["lead"] or p.lead
                s["note"] = s["note"] or p.note
                s["member"] |= member
            continue
        for ref in others:
            agency = ref.split(":", 1)[0]
            if shared:
                link = strong.setdefault(ref, {"ref": ref, "agency": agency, "agency_name": AGENCIES.get(agency, agency),
                                               "tokens": set(), "evidence": []})
                link["tokens"] |= shared
                link["evidence"].append(it["ref"])
            elif overlap:
                sim = similar.setdefault(ref, {"ref": ref, "agency": agency, "agency_name": AGENCIES.get(agency, agency),
                                               "mo_tags": set(), "evidence": []})
                sim["mo_tags"] |= overlap
                sim["evidence"].append(it["ref"])
    for ref in strong:
        similar.pop(ref, None)

    def done(d: dict) -> dict:
        return {k: sorted(v) if isinstance(v, set) else v for k, v in d.items()}

    series_list = sorted((done(s) for s in series.values()), key=lambda s: ("identifier" not in s["basis"], s["series_id"]))
    for s in series_list:
        s["confidence"] = "identifier match" if "identifier" in s["basis"] else "probable (method match)"
    # Cases already in a matched series are shown under that series, not proposed as a new one.
    covered = {ref for s in series_list for ref in s["refs"]}
    return {
        "links": sorted((done(v) for v in strong.values() if v["ref"] not in covered),
                        key=lambda x: (-len(x["tokens"]), x["ref"])),
        "series": series_list,
        "similar": [done(v) for v in similar.values() if v["ref"] not in covered],
        "excluded": [{"token": t, "ref": exclusions[t]["ref"], "memory_id": exclusions[t]["id"]}
                     for t in sorted(tokens & exclusions.keys())],
    }
