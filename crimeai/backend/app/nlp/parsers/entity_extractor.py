"""
spaCy-based NLP Entity Extractor for FIR Documents
----------------------------------------------------
Extracts the following entities from raw FIR text:
  - LOCATION        (GPE, LOC, FAC entities + custom patterns)
  - CRIME_TYPE      (rule-based keyword matching + NER)
  - WEAPON          (rule-based pattern matching)
  - SUSPECT         (PERSON entities + physical description patterns)
  - TIME_REFERENCE  (DATE, TIME entities)
  - VEHICLE         (custom pattern)
  - CASE_DETAILS    (IPC sections, FIR numbers)

Architecture: single spaCy pipeline with custom components layered on top.
Model is loaded once per process (singleton pattern).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.exceptions import NLPServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

_nlp = None


def _get_nlp():
    """Load spaCy model once per process and cache it."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            logger.info("spacy_model_loading", model=settings.SPACY_MODEL)
            _nlp = spacy.load(settings.SPACY_MODEL)
            logger.info("spacy_model_ready", model=settings.SPACY_MODEL)
        except OSError as exc:
            raise NLPServiceError(
                f"spaCy model '{settings.SPACY_MODEL}' not found",
                detail={"hint": f"Run: python -m spacy download {settings.SPACY_MODEL}"},
            ) from exc
        except ImportError as exc:
            raise NLPServiceError(
                "spaCy not installed",
                detail={"hint": "pip install spacy"},
            ) from exc
    return _nlp

# Maps keyword patterns → canonical crime type
_CRIME_KEYWORDS: dict[str, list[str]] = {
    "murder":           ["murder", "killed", "death", "homicide", "deceased", "body found"],
    "assault":          ["assault", "attack", "beat", "beaten", "hit", "punched", "slapped",
                         "physical abuse", "bodily harm"],
    "robbery":          ["robbery", "robbed", "snatched", "loot", "looted", "chain snatching",
                         "mobile snatching", "bag snatching"],
    "theft":            ["theft", "stolen", "stole", "burglary", "pickpocket", "shoplifting",
                         "broke in", "broke into", "pilfered"],
    "kidnapping":       ["kidnap", "kidnapped", "abducted", "abduction", "held hostage",
                         "missing child", "forced into"],
    "fraud":            ["fraud", "cheated", "deceived", "forgery", "fake", "impersonation",
                         "online fraud", "cyber fraud", "phishing", "ponzi"],
    "rape":             ["rape", "sexual assault", "molestation", "outrage of modesty",
                         "sexual abuse", "indecent assault"],
    "drug_offense":     ["drugs", "narcotics", "ganja", "smack", "heroin", "cocaine", "mdma",
                         "contraband", "peddling", "trafficking"],
    "vandalism":        ["vandalism", "damaged", "destroyed property", "broken", "graffiti",
                         "set fire to", "arson"],
    "extortion":        ["extortion", "blackmail", "threatened", "demand money", "ransom"],
    "cybercrime":       ["cyber", "hacking", "hacked", "phishing", "online", "social media",
                         "identity theft", "otp fraud"],
    "trespass":         ["trespass", "trespassing", "illegal entry", "broke in"],
    "domestic_violence":["domestic violence", "wife beating", "husband", "domestic abuse",
                         "dowry", "cruelty"],
    "traffic_violation":["rash driving", "drunk driving", "accident", "hit and run",
                         "red light", "speeding"],
}

_WEAPON_KEYWORDS = [
    "knife", "gun", "pistol", "revolver", "rifle", "sword", "dagger", "axe",
    "rod", "stick", "bat", "hammer", "bottle", "acid", "poison", "bomb",
    "explosive", "firearm", "sharp object", "blunt object", "blade", "machete",
    "iron rod", "lathi", "crowbar", "stone", "country made pistol", "katta",
    "licensed gun",
]

_PHYSICAL_PATTERNS = [
    r"(?:tall|short|medium)\s+(?:build|height|stature)",
    r"(?:fair|dark|wheatish|dusky)\s+(?:complexion|skin)",
    r"(?:young|old|elderly|middle.aged)\s+(?:man|woman|male|female|person)",
    r"aged?\s+(?:about|approximately|around)?\s*\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s*years?",
    r"(?:wearing|dressed\s+in)\s+[a-z\s]+(?:shirt|kurta|jeans|trousers|saree|dupatta)",
    r"(?:bald|bearded|clean.shaven|moustache|long hair|short hair)",
    r"(?:scar|tattoo|birthmark|limping|squint)",
]

_IPC_PATTERN = re.compile(
    r"(?:u/s|under\s+section|section|ipc|sec\.?)\s*(\d+(?:\s*[/,&]\s*\d+)*)",
    re.IGNORECASE,
)

_VEHICLE_PATTERN = re.compile(
    r"\b(?:car|motorcycle|bike|scooter|auto|rickshaw|truck|van|jeep|suv|taxi)\b"
    r"(?:\s+(?:bearing|with|no\.?|number)?\s*(?:registration|reg\.?)?\s*"
    r"(?:no\.?|number)?\s*([A-Z]{2}[-\s]?\d{1,2}[-\s]?[A-Z]{0,3}[-\s]?\d{1,4}))?",
    re.IGNORECASE,
)

_TIME_PATTERNS = [
    r"\b\d{1,2}[:.]\d{2}\s*(?:am|pm|hours?|hrs?)\b",
    r"\b(?:morning|afternoon|evening|night|midnight|dawn|dusk|noon)\b",
    r"\b(?:yesterday|today|last\s+(?:night|week|month))\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
]

@dataclass
class ExtractedEntities:
    locations: list[str] = field(default_factory=list)
    crime_type: str | None = None
    crime_type_confidence: float = 0.0
    weapons: list[str] = field(default_factory=list)
    suspects: list[dict[str, Any]] = field(default_factory=list)
    time_references: list[str] = field(default_factory=list)
    vehicles: list[str] = field(default_factory=list)
    ipc_sections: list[str] = field(default_factory=list)
    persons_mentioned: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    processing_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "locations": self.locations,
            "crime_type": self.crime_type,
            "crime_type_confidence": round(self.crime_type_confidence, 3),
            "weapons": self.weapons,
            "suspects": self.suspects,
            "time_references": self.time_references,
            "vehicles": self.vehicles,
            "ipc_sections": self.ipc_sections,
            "persons_mentioned": self.persons_mentioned,
            "overall_confidence": round(self.overall_confidence, 3),
            "processing_notes": self.processing_notes,
        }

def extract_entities(text: str) -> ExtractedEntities:
    """
    Full NLP pipeline: run spaCy + custom rules on FIR text.

    Returns ExtractedEntities with all fields populated.
    Confidence score reflects how many entity types were found.
    """
    if not text or len(text.strip()) < 10:
        raise NLPServiceError("Text too short for NLP processing", detail={"min_length": 10})

    text_clean = _preprocess_text(text)
    result = ExtractedEntities()

    nlp = _get_nlp()
    doc = nlp(text_clean)

    # Locations: GPE (geo-political entity), LOC (location), FAC (facility)
    seen_locs: set[str] = set()
    for ent in doc.ents:
        normalized = ent.text.strip()
        if ent.label_ in ("GPE", "LOC", "FAC") and normalized not in seen_locs:
            result.locations.append(normalized)
            seen_locs.add(normalized)
        elif ent.label_ == "PERSON":
            if normalized not in result.persons_mentioned:
                result.persons_mentioned.append(normalized)
        elif ent.label_ in ("DATE", "TIME"):
            result.time_references.append(normalized)

    text_lower = text_clean.lower()

    # Crime type detection (keyword matching with scoring)
    crime_scores: dict[str, float] = {}
    for crime_type, keywords in _CRIME_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits > 0:
            # Score = hits / total keywords (normalised)
            crime_scores[crime_type] = hits / len(keywords)

    if crime_scores:
        best_crime = max(crime_scores, key=crime_scores.get)  # type: ignore[arg-type]
        result.crime_type = best_crime
        result.crime_type_confidence = min(crime_scores[best_crime] * 10, 1.0)

    # Weapons
    seen_weapons: set[str] = set()
    for weapon in _WEAPON_KEYWORDS:
        if weapon in text_lower and weapon not in seen_weapons:
            result.weapons.append(weapon)
            seen_weapons.add(weapon)

    # Vehicles
    for match in _VEHICLE_PATTERN.finditer(text_clean):
        vehicle_text = match.group(0).strip()
        if vehicle_text not in result.vehicles:
            result.vehicles.append(vehicle_text[:100])   # cap length

    # IPC sections
    for match in _IPC_PATTERN.finditer(text_clean):
        section = match.group(1).strip()
        if section not in result.ipc_sections:
            result.ipc_sections.append(section)

    # Time references (supplement spaCy with regex)
    for pattern in _TIME_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            ref = match.group(0).strip()
            if ref not in result.time_references:
                result.time_references.append(ref)

    # Suspect physical descriptions
    suspects = _extract_suspect_descriptions(text_clean)
    result.suspects = suspects

    # Additional location extraction from regex if spaCy missed them
    _augment_locations_from_regex(text_clean, result)

    found_fields = sum([
        len(result.locations) > 0,
        result.crime_type is not None,
        len(result.weapons) > 0,
        len(result.suspects) > 0,
        len(result.time_references) > 0,
    ])
    result.overall_confidence = found_fields / 5.0

    if result.overall_confidence < 0.4:
        result.processing_notes.append(
            "Low confidence: limited structured information found in text"
        )

    # Deduplicate lists while preserving order
    result.locations = _deduplicate(result.locations)
    result.time_references = _deduplicate(result.time_references)

    logger.info(
        "nlp_extraction_complete",
        crime_type=result.crime_type,
        n_locations=len(result.locations),
        n_weapons=len(result.weapons),
        n_suspects=len(result.suspects),
        confidence=result.overall_confidence,
    )

    return result


def _preprocess_text(text: str) -> str:
    """Clean FIR text before NLP processing."""
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text.strip())
    # Expand common FIR abbreviations
    abbreviations = {
        r"\bSHO\b": "Station House Officer",
        r"\bFIR\b": "First Information Report",
        r"\bIPC\b": "Indian Penal Code",
        r"\bCrPC\b": "Criminal Procedure Code",
        r"\bPO\b": "Police Officer",
        r"\bInsp\b\.?": "Inspector",
        r"\bSub-Insp\b\.?": "Sub-Inspector",
        r"\bConst\b\.?": "Constable",
        r"\bPS\b": "Police Station",
        r"\bDt\b\.?": "Dated",
        r"\bApprox\b\.?": "approximately",
    }
    for abbr, expansion in abbreviations.items():
        text = re.sub(abbr, expansion, text, flags=re.IGNORECASE)
    return text


def _extract_suspect_descriptions(text: str) -> list[dict[str, Any]]:
    """Extract structured suspect/accused descriptions from text."""
    suspects = []
    # Find description blocks (sentences mentioning accused/suspect/person)
    sentences = re.split(r"[.!?;]", text)
    for sentence in sentences:
        sent_lower = sentence.lower()
        if not any(kw in sent_lower for kw in [
            "accused", "suspect", "perpetrator", "offender",
            "attacker", "assailant", "named", "unknown person",
        ]):
            continue

        suspect: dict[str, Any] = {"raw_description": sentence.strip()[:300]}

        # Extract age
        age_match = re.search(
            r"aged?\s+(?:about|approximately|around)?\s*(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*years?",
            sent_lower,
        )
        if age_match:
            suspect["age"] = f"{age_match.group(1)}"
            if age_match.group(2):
                suspect["age"] += f"–{age_match.group(2)}"

        # Extract gender
        if any(kw in sent_lower for kw in ["female", "woman", "girl", "she", "her"]):
            suspect["gender"] = "female"
        elif any(kw in sent_lower for kw in ["male", "man", "boy", "he", "him"]):
            suspect["gender"] = "male"

        # Extract build
        for build_kw in ["tall", "short", "medium build", "stout", "slim", "thin"]:
            if build_kw in sent_lower:
                suspect["build"] = build_kw
                break

        # Extract complexion
        for comp_kw in ["fair", "dark", "wheatish", "dusky"]:
            if comp_kw in sent_lower:
                suspect["complexion"] = comp_kw
                break

        # Extract clothing keywords
        clothing = []
        for cloth_kw in ["shirt", "kurta", "jeans", "trousers", "jacket", "cap", "helmet"]:
            if cloth_kw in sent_lower:
                clothing.append(cloth_kw)
        if clothing:
            suspect["clothing"] = clothing

        if len(suspect) > 1:   # Has more than just raw_description
            suspects.append(suspect)

    return suspects[:5]   # Cap at 5 suspects per FIR


def _augment_locations_from_regex(text: str, result: ExtractedEntities) -> None:
    """Add location hints that spaCy's NER might miss (Indian addresses)."""
    # Police station / area references
    ps_pattern = re.compile(
        r"(?:Police Station|P\.S\.|PS|Thana)\s+([A-Z][a-zA-Z\s]{2,40})",
    )
    for match in ps_pattern.finditer(text):
        loc = f"PS {match.group(1).strip()}"
        if loc not in result.locations:
            result.locations.append(loc)

    # Near / in front of / behind references
    near_pattern = re.compile(
        r"(?:near|opposite|in front of|behind|adjacent to)\s+([A-Z][a-zA-Z\s]{3,50})",
    )
    for match in near_pattern.finditer(text):
        loc = match.group(1).strip()
        if loc not in result.locations and len(loc) > 3:
            result.locations.append(loc)


def _deduplicate(items: list[str]) -> list[str]:
    """Remove duplicates while preserving insertion order."""
    seen: set[str] = set()
    result = []
    for item in items:
        key = item.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
