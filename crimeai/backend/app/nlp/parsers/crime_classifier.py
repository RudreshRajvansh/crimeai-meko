"""
Crime Type Classifier
----------------------
Two-layer classification approach:
  1. Rule-based keyword matching (fast, no model needed) — primary
  2. Zero-shot classification via HuggingFace transformers — fallback for
     ambiguous cases where keyword matching has low confidence

The zero-shot model is loaded lazily and only used when keyword
confidence is below the threshold (0.4).

For production: the zero-shot model can be replaced with a fine-tuned
classifier once enough labelled FIR data is collected.
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.nlp.parsers.entity_extractor import _CRIME_KEYWORDS

logger = get_logger(__name__)

# Threshold below which we invoke the heavy zero-shot model
_FALLBACK_THRESHOLD = 0.35

# Candidate labels for zero-shot classification
_ZERO_SHOT_LABELS = [
    "theft and burglary",
    "violent assault",
    "robbery and snatching",
    "murder and homicide",
    "kidnapping and abduction",
    "fraud and financial crime",
    "drug trafficking and possession",
    "sexual offense",
    "cybercrime and online fraud",
    "vandalism and property damage",
    "domestic violence",
    "traffic violation",
    "extortion and blackmail",
]

# Mapping zero-shot labels → canonical crime types
_LABEL_TO_TYPE: dict[str, str] = {
    "theft and burglary": "theft",
    "violent assault": "assault",
    "robbery and snatching": "robbery",
    "murder and homicide": "murder",
    "kidnapping and abduction": "kidnapping",
    "fraud and financial crime": "fraud",
    "drug trafficking and possession": "drug_offense",
    "sexual offense": "sexual_offense",
    "cybercrime and online fraud": "cybercrime",
    "vandalism and property damage": "vandalism",
    "domestic violence": "domestic_violence",
    "traffic violation": "traffic_violation",
    "extortion and blackmail": "extortion",
}

# Lazy-loaded zero-shot classifier
_classifier = None


def _get_zero_shot_classifier():
    """Lazily load HuggingFace zero-shot classifier."""
    global _classifier
    if _classifier is None:
        try:
            from transformers import pipeline
            logger.info("zero_shot_classifier_loading")
            _classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1,   # CPU; set to 0 for GPU
            )
            logger.info("zero_shot_classifier_ready")
        except ImportError:
            logger.warning(
                "transformers_not_installed",
                hint="pip install transformers — zero-shot fallback disabled",
            )
            return None
        except Exception as exc:
            logger.warning("zero_shot_classifier_failed", error=str(exc))
            return None
    return _classifier


def classify_crime_type(
    text: str,
    keyword_crime_type: str | None = None,
    keyword_confidence: float = 0.0,
) -> dict[str, Any]:
    """
    Classify crime type from FIR text.

    Args:
        text: raw FIR text
        keyword_crime_type: crime type already detected by keyword matching
        keyword_confidence: confidence from keyword matching (0–1)

    Returns dict with:
        crime_type, confidence, method, top_predictions
    """
    text_lower = text.lower()

    hits: dict[str, int] = {}
    for crime_type, keywords in _CRIME_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count:
            hits[crime_type] = count

    # Confidence is the share of keyword evidence for the winning type, discounted
    # when that evidence is a single keyword. A lone weak hit is not certainty.
    total_hits = sum(hits.values())
    crime_scores: dict[str, float] = {
        k: (v / total_hits) * min(1.0, v / 2) for k, v in hits.items()
    }

    best_keyword_type = max(crime_scores, key=crime_scores.get) if crime_scores else None  # type: ignore[arg-type]
    best_keyword_conf = crime_scores.get(best_keyword_type, 0.0) if best_keyword_type else 0.0

    top_keyword_predictions = sorted(
        [{"crime_type": k, "score": round(v, 3)} for k, v in crime_scores.items()],
        key=lambda x: x["score"],
        reverse=True,
    )[:5]

    zero_shot_result = None
    method = "keyword"

    if settings.ENABLE_ZERO_SHOT and best_keyword_conf < _FALLBACK_THRESHOLD and len(text) >= 50:
        classifier = _get_zero_shot_classifier()
        if classifier is not None:
            try:
                truncated = text[:512]
                output = classifier(
                    truncated,
                    candidate_labels=_ZERO_SHOT_LABELS,
                    multi_label=False,
                )
                top_label = output["labels"][0]
                top_score = float(output["scores"][0])
                canonical_type = _LABEL_TO_TYPE.get(top_label, "other")

                zero_shot_result = {
                    "crime_type": canonical_type,
                    "label": top_label,
                    "confidence": round(top_score, 3),
                    "all_labels": [
                        {"label": lbl, "score": round(sc, 3)}
                        for lbl, sc in zip(output["labels"][:5], output["scores"][:5], strict=False)
                    ],
                }
                method = "zero_shot"
                logger.info(
                    "zero_shot_classification_used",
                    crime_type=canonical_type,
                    confidence=top_score,
                )
            except Exception as exc:
                logger.warning("zero_shot_classification_failed", error=str(exc))

    if zero_shot_result and zero_shot_result["confidence"] > best_keyword_conf:
        final_type = zero_shot_result["crime_type"]
        final_confidence = zero_shot_result["confidence"]
    elif best_keyword_type:
        final_type = best_keyword_type
        final_confidence = best_keyword_conf
    else:
        final_type = "other"
        final_confidence = 0.0
        method = "default"

    return {
        "crime_type": final_type,
        "confidence": round(final_confidence, 3),
        "method": method,
        "keyword_predictions": top_keyword_predictions,
        "zero_shot_result": zero_shot_result,
    }


def classify_severity(
    crime_type: str,
    has_weapon: bool = False,
    has_injury: bool = False,
    num_suspects: int = 1,
    text: str = "",
) -> int:
    """
    Infer severity (1–5) from crime attributes.
    Used when severity is not explicitly provided.
    """
    # Base severity per crime type
    base_severity: dict[str, int] = {
        "murder": 5,
        "kidnapping": 5,
        "sexual_offense": 5,
        "robbery": 4,
        "assault": 3,
        "domestic_violence": 4,
        "extortion": 3,
        "fraud": 3,
        "cybercrime": 2,
        "drug_offense": 3,
        "theft": 2,
        "vandalism": 2,
        "trespass": 1,
        "traffic_violation": 2,
        "other": 2,
    }
    severity = base_severity.get(crime_type, 2)

    # Adjustments
    if has_weapon:
        severity = min(5, severity + 1)
    if has_injury:
        severity = min(5, severity + 1)
    if num_suspects > 3:
        severity = min(5, severity + 1)

    # Text signals
    text_lower = text.lower()
    if any(w in text_lower for w in ["grievous", "critical", "life threatening", "gang"]):
        severity = min(5, severity + 1)

    return severity
