"""
Language-agnostic FIR understanding.

Works on text in any of the 22 scheduled languages or English:

1. Detect the script from Unicode blocks, then the language, using marker words
   where several languages share a script (Hindi, Marathi, Nepali, Konkani...
   all use Devanagari; Urdu, Kashmiri and Sindhi share the Arabic script).
2. Normalise Indic digits (०१२, ০১২, ௧௨௩ ...) to ASCII. This is a one-to-one
   code-point mapping, so character offsets survive and highlights stay aligned.
3. Find crime, weapon, legal and place terms from the lexicons, each with an
   English gloss, as character spans the UI can highlight in the original text.
4. Pull out language-neutral identifiers that link cases together: vehicle
   registration numbers (always Latin on Indian plates), phone numbers, UPI IDs
   and amounts.

Deep semantics (similarity, cross-language linking) come from the multilingual
embedding model; this layer gives exact, explainable signals.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from app.nlp.lexicons import (
    CODE_WORDS,
    CRIME_LABELS,
    CRIME_TERMS,
    ENGLISH_CRIME_TERMS,
    ENGLISH_WEAPON_TERMS,
    LANGUAGES,
    MARKERS,
    POLICE_STATION_WORDS,
    SECTION_WORDS,
    TERM_GLOSSES,
    WEAK_EVIDENCE_TERMS,
    WEAPON_TERMS,
)

_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "Devanagari"),
    (0x0980, 0x09FF, "Bengali"),
    (0x0A00, 0x0A7F, "Gurmukhi"),
    (0x0A80, 0x0AFF, "Gujarati"),
    (0x0B00, 0x0B7F, "Odia"),
    (0x0B80, 0x0BFF, "Tamil"),
    (0x0C00, 0x0C7F, "Telugu"),
    (0x0C80, 0x0CFF, "Kannada"),
    (0x0D00, 0x0D7F, "Malayalam"),
    (0x0600, 0x06FF, "Arabic"),
    (0x0750, 0x077F, "Arabic"),
    (0x1C50, 0x1C7F, "Ol Chiki"),
    (0xABC0, 0xABFF, "Meetei Mayek"),
]
_SCRIPT_DEFAULT_LANGUAGE = {
    "Devanagari": "hi", "Bengali": "bn", "Gurmukhi": "pa", "Gujarati": "gu", "Odia": "or", "Tamil": "ta",
    "Telugu": "te", "Kannada": "kn", "Malayalam": "ml", "Arabic": "ur", "Ol Chiki": "sat",
    "Meetei Mayek": "mni", "Latin": "en",
}
_SHARED_SCRIPT_CANDIDATES = {
    "Devanagari": ["hi", "mr", "ne", "kok", "mai", "doi", "brx", "sa"],
    "Arabic": ["ur", "ks", "sd"],
    "Latin": ["en", "hi-Latn"],
}
_ASSAMESE_LETTERS = {"ৰ", "ৱ"}

# The series may be split, as on Delhi two-wheeler plates: "DL 3S CK 4471".
_VEHICLE = re.compile(r"\b([A-Z]{2})[\s-]?(\d{1,2})[\s-]?([A-Z]{1,3}(?:[\s-]?[A-Z]{1,2})?)[\s-]?(\d{4})\b")
_TOKEN_SPLIT = re.compile(r"[\s.,;:!?()\[\]\"'।॥۔،-]+")
_BH_VEHICLE = re.compile(r"\b(\d{2})[\s-]?BH[\s-]?(\d{4})[\s-]?([A-Z]{1,2})\b")
_PHONE = re.compile(r"(?<![\d+])(?:\+91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?!\d)")
_UPI = re.compile(r"\b[\w.-]{2,64}@(?:ok[a-z]+|ybl|ibl|axl|apl|upi|paytm|airtel|jio|[a-z]{2,10}bank)\b", re.I)
_FIR_REF = re.compile(r"\bF\.?\s?I\.?\s?R\.?\s*(?:No\.?|Number|#)?\s*[:.-]?\s*(\d{1,5})\s*/\s*((?:19|20)\d{2})\b", re.I)
_DATE = re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.]((?:19|20)\d{2})(?!\d)")
_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr|रु\.?|रू\.?|રૂ\.?|रुपये|रुपए|রুপি|ரூபாய்|రూపాయలు|રૂપિયા|ರೂಪಾಯಿ|രൂപ|ਰੁਪਏ|ଟଙ୍କା|روپے)\s*([\d,]+(?:\.\d+)?)"
    r"|([\d,]+(?:\.\d+)?)\s*(?:₹|rs\.?|rupees|रुपये|रुपए|লাখ|lakh|crore)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Highlight:
    start: int
    end: int
    text: str
    kind: str  # crime | weapon | legal | place | vehicle | phone | upi | amount | reference | date
    gloss: str
    language: str


@dataclass(slots=True)
class MultilingualAnalysis:
    language: str
    language_name: str
    script: str
    confidence: float
    is_mixed: bool
    crime_type: str | None
    crime_scores: dict[str, float]
    weapons: list[str]
    vehicles: list[str]
    phones: list[str]
    upi_ids: list[str]
    amounts: list[float]
    fir_references: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["highlights"] = [asdict(h) for h in self.highlights]
        return data


def normalise_digits(text: str) -> str:
    """Map every Unicode decimal digit to ASCII. One code point in, one out, so offsets are preserved."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch for ch in text)


def script_profile(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for ch in text:
        cp = ord(ch)
        if ch.isascii():
            if ch.isalpha():
                counts["Latin"] += 1
            continue
        for low, high, script in _SCRIPT_RANGES:
            if low <= cp <= high:
                counts[script] += 1
                break
    return counts


def _tokens(text: str) -> list[str]:
    # Not \w+: Python's \w splits Indic words at vowel signs (combining marks), turning
    # Hindi words into fragments that falsely match other languages' marker words.
    return [t for t in _TOKEN_SPLIT.split(text.lower()) if t]


def _marker_score(text: str, language: str) -> int:
    tokens = _tokens(text)
    vocabulary = set(MARKERS.get(language, []))
    return sum(1 for t in tokens if t in vocabulary)


def detect_language(text: str) -> tuple[str, str, float, bool]:
    """Returns (language code, script, confidence 0-1, mixed-script flag)."""
    profile = script_profile(text)
    if not profile:
        return "en", "Latin", 0.0, False
    total = sum(profile.values())
    script, count = profile.most_common(1)[0]
    # Indic text routinely carries Latin vehicle numbers and English loanwords; prefer the Indic script
    # when it holds a meaningful share.
    indic = [(s, c) for s, c in profile.most_common() if s != "Latin"]
    if script == "Latin" and indic and indic[0][1] / total >= 0.25:
        script, count = indic[0]
    mixed = len([c for c in profile.values() if c / total >= 0.15]) > 1

    if script == "Bengali" and any(ch in _ASSAMESE_LETTERS for ch in text):
        return "as", script, round(count / total, 2), mixed
    candidates = _SHARED_SCRIPT_CANDIDATES.get(script)
    if not candidates:
        return _SCRIPT_DEFAULT_LANGUAGE.get(script, "en"), script, round(count / total, 2), mixed

    scores = {lang: _marker_score(text, lang) for lang in candidates}
    best = max(scores, key=lambda lang: scores[lang])
    if scores[best] == 0:
        best = _SCRIPT_DEFAULT_LANGUAGE[script]
    if script == "Latin" and best == "hi-Latn" and scores["hi-Latn"] < 2:
        best = "en"
    margin = scores[best] / (sum(scores.values()) or 1)
    confidence = round(min(1.0, (count / total) * (0.6 + 0.4 * margin)), 2)
    return best, script, confidence, mixed


_JOINERS = "[‌‍]?"


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern[str]:
    """
    Match a term even when invisible zero-width (non-)joiners sit between its characters, as Indic OCR
    output and many Indic keyboards insert them. Matching the original string keeps offsets exact.
    """
    return re.compile(_JOINERS.join(re.escape(ch) for ch in term))


def _find_terms(text: str, terms: dict[str, str], kind: str, language: str, gloss_fn) -> list[Highlight]:
    found: list[Highlight] = []
    lowered = text.lower()
    for term, concept in terms.items():
        needle = term.lower()
        latin = needle.isascii()
        for match in _term_pattern(needle).finditer(lowered):
            start, end = match.span()
            if latin:
                if start > 0 and lowered[start - 1].isalnum():
                    continue
                suffix_ok = kind == "crime" and lowered[end:end + 1] == "s"
                if end < len(lowered) and lowered[end].isalnum() and not suffix_ok:
                    continue
            gloss = TERM_GLOSSES.get(needle) if kind == "crime" else None
            found.append(Highlight(start, end, text[start:end], kind, gloss or gloss_fn(concept), language))
    return found


def _dedupe(highlights: list[Highlight]) -> list[Highlight]:
    """Keep the longest span where spans overlap (e.g. 'मोटरसाइकिल चोरी' over 'चोरी')."""
    ordered = sorted(highlights, key=lambda h: (h.start, -(h.end - h.start)))
    kept: list[Highlight] = []
    last_end = -1
    for h in ordered:
        if h.start >= last_end:
            kept.append(h)
            last_end = h.end
    return kept


def analyse(text: str) -> MultilingualAnalysis:
    original = text or ""
    digits = normalise_digits(original)
    language, script, confidence, mixed = detect_language(original)
    lexicon_langs = {language} if language in CRIME_TERMS else set()
    if script == "Devanagari":
        lexicon_langs |= {"hi", "mr"}  # Devanagari languages share most crime and legal vocabulary
    elif script == "Bengali":
        lexicon_langs |= {"bn", "as"}
    elif script == "Latin":
        lexicon_langs |= {"hi-Latn"}

    highlights: list[Highlight] = []
    crime_terms = dict(ENGLISH_CRIME_TERMS)
    weapon_terms = dict(ENGLISH_WEAPON_TERMS)
    for lang in lexicon_langs:
        crime_terms.update(CRIME_TERMS.get(lang, {}))
        weapon_terms.update(WEAPON_TERMS.get(lang, {}))

    highlights += _find_terms(original, crime_terms, "crime", language, lambda c: CRIME_LABELS.get(c, c))
    highlights += _find_terms(original, weapon_terms, "weapon", language, lambda w: w)
    highlights += _find_terms(original, dict.fromkeys(SECTION_WORDS, "section"), "legal", language, lambda _: "section")
    highlights += _find_terms(original, CODE_WORDS, "legal", language, lambda code: f"{code} (penal code)")
    highlights += _find_terms(original, dict.fromkeys(POLICE_STATION_WORDS, "police station"), "place", language,
                              lambda _: "police station")

    vehicles: list[str] = []
    for pattern in (_VEHICLE, _BH_VEHICLE):
        for m in pattern.finditer(digits):
            plate = re.sub(r"[\s-]", "", "".join(m.groups()))
            vehicles.append(plate)
            highlights.append(Highlight(m.start(), m.end(), original[m.start():m.end()], "vehicle", f"vehicle {plate}", language))
    phones = []
    for m in _PHONE.finditer(digits):
        number = "".join(m.groups())
        phones.append(number)
        highlights.append(Highlight(m.start(), m.end(), original[m.start():m.end()], "phone", "phone number", language))
    upi_ids = []
    for m in _UPI.finditer(digits):
        upi_ids.append(m.group(0).lower())
        highlights.append(Highlight(m.start(), m.end(), original[m.start():m.end()], "upi", "UPI ID", language))
    amounts = []
    for m in _AMOUNT.finditer(digits):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            amounts.append(float(raw))
        except ValueError:
            continue
        highlights.append(Highlight(m.start(), m.end(), original[m.start():m.end()], "amount", f"amount ₹{raw}", language))

    fir_refs = []
    for m in _FIR_REF.finditer(digits):
        ref = f"{int(m.group(1))}/{m.group(2)}"
        fir_refs.append(ref)
        highlights.append(Highlight(m.start(), m.end(), original[m.start():m.end()], "reference", f"FIR {ref}", language))
    dates = []
    for m in _DATE.finditer(digits):
        day, month, year = (int(g) for g in m.groups())
        if 1 <= day <= 31 and 1 <= month <= 12:
            iso = f"{year:04d}-{month:02d}-{day:02d}"
            dates.append(iso)
            highlights.append(Highlight(m.start(), m.end(), original[m.start():m.end()], "date", f"date {iso}", language))

    highlights = _dedupe(highlights)
    crime_counts: Counter[str] = Counter()
    for h in highlights:
        term = h.text.lower()
        if h.kind == "crime" and term in crime_terms:
            crime_counts[crime_terms[term]] += 0.5 if term in WEAK_EVIDENCE_TERMS else 1.0
    total = sum(crime_counts.values())
    scores = {k: round(v / total, 3) for k, v in crime_counts.most_common()} if total else {}
    weapons = sorted({h.gloss for h in highlights if h.kind == "weapon"})

    return MultilingualAnalysis(
        language=language,
        language_name=LANGUAGES.get(language, {}).get("name", language),
        script=script,
        confidence=confidence,
        is_mixed=mixed,
        crime_type=next(iter(scores), None),
        crime_scores=scores,
        weapons=weapons,
        vehicles=sorted(set(vehicles)),
        phones=sorted(set(phones)),
        upi_ids=sorted(set(upi_ids)),
        amounts=amounts,
        fir_references=sorted(set(fir_refs)),
        dates=sorted(set(dates)),
        highlights=highlights,
    )


def normalise_for_legal(text: str) -> str:
    """Rewrite native section/code words to English so the IPC/BNS parser reads every language."""
    out = normalise_digits(text)
    for word, code in sorted(CODE_WORDS.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(word, f" {code} ")
    for word in sorted(SECTION_WORDS, key=len, reverse=True):
        out = re.sub(re.escape(word), " section ", out, flags=re.I)
    return out
