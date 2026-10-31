"""
IPC -> BNS section crosswalk.

The Bharatiya Nyaya Sanhita, 2023 replaced the Indian Penal Code for offences
committed on or after 1 July 2024. During the transition FIRs cite either code,
sometimes both, and sometimes the wrong one for the incident date. This module
extracts cited sections, decides which code governs the incident, maps IPC
sections to their BNS counterparts and flags citations that look wrong.

The table covers the sections that dominate FIR volume. It must be reviewed
against the official MHA/BPR&D correspondence table before being relied on
for charging decisions; the API labels it as decision support only.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime

BNS_COMMENCEMENT = date(2024, 7, 1)

# ipc_section: (bns_section, offence, typical crime_type)
IPC_TO_BNS: dict[str, tuple[str, str, str]] = {
    "34": ("3(5)", "Acts done by several persons in furtherance of common intention", "other"),
    "120B": ("61(2)", "Criminal conspiracy", "other"),
    "147": ("191(2)", "Rioting", "assault"),
    "148": ("191(3)", "Rioting armed with deadly weapon", "assault"),
    "149": ("190", "Unlawful assembly: common object", "assault"),
    "201": ("238", "Causing disappearance of evidence", "other"),
    "279": ("281", "Rash driving on a public way", "traffic_violation"),
    "302": ("103(1)", "Murder", "murder"),
    "304": ("105", "Culpable homicide not amounting to murder", "murder"),
    "304A": ("106(1)", "Causing death by negligence", "traffic_violation"),
    "304B": ("80", "Dowry death", "domestic_violence"),
    "306": ("108", "Abetment of suicide", "other"),
    "307": ("109", "Attempt to murder", "assault"),
    "323": ("115(2)", "Voluntarily causing hurt", "assault"),
    "324": ("118(1)", "Voluntarily causing hurt by dangerous weapons", "assault"),
    "325": ("117(2)", "Voluntarily causing grievous hurt", "assault"),
    "341": ("126(2)", "Wrongful restraint", "assault"),
    "342": ("127(2)", "Wrongful confinement", "kidnapping"),
    "354": ("74", "Assault or criminal force to outrage a woman's modesty", "sexual_offense"),
    "354A": ("75", "Sexual harassment", "sexual_offense"),
    "354D": ("78", "Stalking", "sexual_offense"),
    "363": ("137(2)", "Kidnapping", "kidnapping"),
    "366": ("87", "Kidnapping a woman to compel marriage", "kidnapping"),
    "376": ("64", "Rape", "sexual_offense"),
    "376D": ("70(1)", "Gang rape", "sexual_offense"),
    "379": ("303(2)", "Theft", "theft"),
    "380": ("305", "Theft in a dwelling house", "burglary"),
    "384": ("308(2)", "Extortion", "extortion"),
    "392": ("309(4)", "Robbery", "robbery"),
    "395": ("310(2)", "Dacoity", "robbery"),
    "406": ("316(2)", "Criminal breach of trust", "fraud"),
    "411": ("317(2)", "Dishonestly receiving stolen property", "theft"),
    "420": ("318(4)", "Cheating and dishonestly inducing delivery of property", "fraud"),
    "427": ("324(4)", "Mischief causing damage", "vandalism"),
    "447": ("329(3)", "Criminal trespass", "trespass"),
    "448": ("329(4)", "House-trespass", "trespass"),
    "467": ("338", "Forgery of valuable security or will", "fraud"),
    "468": ("336(3)", "Forgery for the purpose of cheating", "fraud"),
    "471": ("340(2)", "Using a forged document as genuine", "fraud"),
    "498A": ("85", "Cruelty by husband or relatives", "domestic_violence"),
    "506": ("351(2)", "Criminal intimidation", "extortion"),
    "509": ("79", "Word, gesture or act intended to insult a woman's modesty", "sexual_offense"),
    "511": ("62", "Attempt to commit offences", "other"),
}

NO_BNS_EQUIVALENT = {
    "377": "Unnatural offences: no general equivalent in BNS",
    "124A": "Sedition: repealed; BNS s.152 covers a different, narrower offence",
    "497": "Adultery: struck down (Joseph Shine, 2018); not in BNS",
    "309": "Attempt to suicide: not carried into BNS",
}

_SECTION = r"\d{1,3}[A-Z]{0,2}(?:\(\d+\))?"
_CODE = r"IPC|I\.P\.C\.?|BNS|Indian\s+Penal\s+Code|Bharatiya\s+Nyaya\s+Sanhita"
_CITATION = re.compile(
    rf"(?:(?P<code_before>{_CODE})\s+)?"
    rf"(?:u/s|u/ss|under\s+sections?|sections?|secs?\.?|s\.)\s*"
    rf"(?P<sections>{_SECTION}(?:\s*(?:,|/|&|and)\s*{_SECTION})*)"
    rf"(?:\s*(?:of\s+)?(?:the\s+)?(?P<code>{_CODE}))?",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"\s*(?:,|/|&|and)\s*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SectionCitation:
    section: str
    code: str | None


@dataclass(frozen=True, slots=True)
class MappedSection:
    ipc: str | None
    bns: str | None
    offence: str | None
    crime_type: str | None
    note: str | None = None


def _normalise_code(raw: str | None) -> str | None:
    if not raw:
        return None
    return "BNS" if raw.upper().startswith(("BNS", "BHARATIYA")) else "IPC"


def extract_citations(text: str) -> list[SectionCitation]:
    seen: dict[tuple[str, str | None], SectionCitation] = {}
    for match in _CITATION.finditer(text or ""):
        code = _normalise_code(match.group("code") or match.group("code_before"))
        for section in _SPLIT.split(match.group("sections")):
            section = section.strip().upper()
            if section:
                seen.setdefault((section, code), SectionCitation(section, code))
    return list(seen.values())


def governing_code(incident_date: date | datetime | None) -> str:
    if incident_date is None:
        return "BNS"
    day = incident_date.date() if isinstance(incident_date, datetime) else incident_date
    return "BNS" if day >= BNS_COMMENCEMENT else "IPC"


def _bns_lookup(section: str) -> MappedSection:
    for ipc, (bns, offence, crime_type) in IPC_TO_BNS.items():
        if bns == section or bns.split("(")[0] == section:
            return MappedSection(ipc=ipc, bns=bns, offence=offence, crime_type=crime_type)
    return MappedSection(ipc=None, bns=section, offence=None, crime_type=None, note="Not in the crosswalk table")


def _ipc_lookup(section: str) -> MappedSection:
    base = section.split("(")[0]
    if base in IPC_TO_BNS:
        bns, offence, crime_type = IPC_TO_BNS[base]
        return MappedSection(ipc=base, bns=bns, offence=offence, crime_type=crime_type)
    if base in NO_BNS_EQUIVALENT:
        return MappedSection(ipc=base, bns=None, offence=None, crime_type=None, note=NO_BNS_EQUIVALENT[base])
    return MappedSection(ipc=base, bns=None, offence=None, crime_type=None, note="Not in the crosswalk table")


def analyse_sections(text: str, incident_date: date | datetime | None = None) -> dict:
    regime = governing_code(incident_date)
    citations = extract_citations(text)
    mapped: list[MappedSection] = []
    warnings: list[str] = []

    for citation in citations:
        code = citation.code or regime
        if citation.code is None and incident_date is None and citation.section.split("(")[0] in IPC_TO_BNS:
            # Undated and uncoded: the older numbering is far more common in historical records.
            code = "IPC"
        entry = _bns_lookup(citation.section) if code == "BNS" else _ipc_lookup(citation.section)
        mapped.append(entry)
        if citation.code == "IPC" and regime == "BNS":
            target = f"BNS s.{entry.bns}" if entry.bns else "a BNS provision"
            warnings.append(
                f"IPC s.{citation.section} cited for an incident on or after 1 July 2024; consider {target}"
            )
        if citation.code == "BNS" and regime == "IPC":
            warnings.append(
                f"BNS s.{citation.section} cited for an incident before 1 July 2024, which IPC governs"
            )

    crime_types = [m.crime_type for m in mapped if m.crime_type and m.crime_type != "other"]
    return {
        "governing_code": regime,
        "citations": [asdict(c) for c in citations],
        "mapped": [asdict(m) for m in mapped],
        "suggested_crime_type": max(set(crime_types), key=crime_types.count) if crime_types else None,
        "warnings": warnings,
        "disclaimer": "Decision support only. Verify against the official IPC-BNS correspondence table.",
    }
