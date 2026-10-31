"""
FIR analysis pipeline, for FIRs in any of the 22 scheduled languages or English.

text -> language + script -> entities (spaCy for English, multilingual lexicons otherwise)
     -> legal sections in native words and digits (IPC/BNS crosswalk)
     -> crime type (keywords, legal sections, optional zero-shot)
     -> severity -> PII-redacted copy

The output is stored as JSONB on the FIR and versioned by PIPELINE_VERSION so
records processed by older logic can be found and reprocessed.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import NLPServiceError
from app.core.logging import get_logger
from app.nlp.legal.bns_crosswalk import analyse_sections
from app.nlp.multilingual import analyse, normalise_digits, normalise_for_legal
from app.nlp.parsers.crime_classifier import classify_crime_type, classify_severity
from app.nlp.parsers.entity_extractor import ExtractedEntities, extract_entities
from app.nlp.privacy.redaction import redact

logger = get_logger(__name__)

PIPELINE_VERSION = "3.0.0"
_LEGAL_SIGNAL_CONFIDENCE = 0.8

_INJURY_KEYWORDS = (
    "injured", "injury", "hurt", "wound", "wounded", "bleeding", "fracture", "broken bone",
    "hospitalised", "hospitalized", "grievous hurt", "bodily harm", "medical treatment",
    "unconscious", "dead", "death", "deceased",
)


def _mentions_injury(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _INJURY_KEYWORDS)


def _mask(value: str, keep: int = 3) -> str:
    return value[:2] + "•" * max(len(value) - 2 - keep, 0) + value[-keep:]


def process_fir_text(
    text: str,
    fir_number: str | None = None,
    incident_date: datetime | None = None,
) -> dict[str, Any]:
    if not text or len(text.strip()) < 20:
        raise NLPServiceError("FIR text too short for processing", detail={"min_length": 20})

    lang = analyse(text)
    english = lang.script == "Latin" and lang.language == "en"
    if english:
        try:
            entities: ExtractedEntities = extract_entities(text)
        except NLPServiceError:
            raise
        except Exception as exc:
            raise NLPServiceError("Entity extraction failed", detail={"error": str(exc)}) from exc
    else:
        # The spaCy model is English-only; for Indian-language FIRs the multilingual lexicon layer
        # supplies crime, weapon and identifier signals, and embeddings carry the semantics.
        entities = ExtractedEntities(
            crime_type=lang.crime_type,
            crime_type_confidence=max(lang.crime_scores.values(), default=0.0) * 0.8,
            weapons=lang.weapons,
            vehicles=lang.vehicles,
            overall_confidence=round(0.4 + 0.3 * bool(lang.crime_type) + 0.3 * lang.confidence, 3),
            processing_notes=[f"Analysed with the {lang.language_name} lexicon and multilingual embeddings"],
        )

    legal = analyse_sections(normalise_for_legal(text), incident_date)
    classification = classify_crime_type(
        text=text,
        keyword_crime_type=entities.crime_type,
        keyword_confidence=entities.crime_type_confidence,
    )

    crime_type, confidence, method = entities.crime_type, entities.crime_type_confidence, (
        "entity_rules" if english else f"lexicon:{lang.language}"
    )
    if english and classification["confidence"] > confidence:
        crime_type, confidence, method = classification["crime_type"], classification["confidence"], classification["method"]
    # Cited penal sections are stronger evidence of the offence than narrative keywords.
    if legal["suggested_crime_type"] and confidence < _LEGAL_SIGNAL_CONFIDENCE:
        crime_type, confidence, method = legal["suggested_crime_type"], _LEGAL_SIGNAL_CONFIDENCE, "legal_sections"

    has_injury = _mentions_injury(text)
    weapons = sorted(set(entities.weapons) | set(lang.weapons))
    severity = classify_severity(
        crime_type=crime_type or "other",
        has_weapon=bool(weapons),
        has_injury=has_injury,
        num_suspects=len(entities.suspects),
        text=text,
    )
    redaction = redact(normalise_digits(text))

    result = {
        "language": {
            "code": lang.language,
            "name": lang.language_name,
            "script": lang.script,
            "confidence": lang.confidence,
            "mixed_script": lang.is_mixed,
        },
        "locations": entities.locations,
        "primary_location": entities.locations[0] if entities.locations else None,
        "crime_type": crime_type,
        "crime_type_confidence": round(confidence or 0.0, 3),
        "classification": {
            "method": method,
            "keyword_predictions": classification["keyword_predictions"] if english else [
                {"crime_type": k, "score": v} for k, v in lang.crime_scores.items()
            ],
        },
        "weapons": weapons,
        "suspects": entities.suspects,
        "time_references": entities.time_references,
        "identifiers": {
            "vehicles": sorted(set(entities.vehicles) | set(lang.vehicles)),
            "phones": [_mask(p) for p in lang.phones],
            "upi_ids": [_mask(u.split("@")[0]) + "@" + u.split("@")[1] for u in lang.upi_ids],
            "amounts": lang.amounts,
            "fir_references": lang.fir_references,
            "dates": lang.dates,
        },
        "persons_mentioned_count": len(entities.persons_mentioned),
        "legal": legal,
        "inferred_severity": severity,
        "has_weapon": bool(weapons),
        "has_injury": has_injury,
        "num_suspects": len(entities.suspects),
        "privacy": {"pii_found": redaction.counts},
        "overall_confidence": round(entities.overall_confidence, 3),
        "processing_notes": entities.processing_notes,
        "processed_at": datetime.now(UTC).isoformat(),
        "fir_number": fir_number,
        "text_length": len(text),
        "pipeline_version": PIPELINE_VERSION,
    }
    logger.info(
        "fir_pipeline_complete",
        fir_number=fir_number,
        language=lang.language,
        crime_type=crime_type,
        legal_warnings=len(legal["warnings"]),
        pii_types=sorted(redaction.counts),
    )
    return {"entities": result, "redacted_text": redaction.text}
