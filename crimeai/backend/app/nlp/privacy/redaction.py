"""
PII redaction for FIR narratives.

FIRs routinely contain Aadhaar numbers, phone numbers, PAN, bank and UPI
details of complainants and witnesses. Under the Digital Personal Data
Protection Act, 2023 that data should be exposed only where the purpose needs
it. Redacted text is what goes into embeddings, analyst views and exports;
the original stays in the record for investigating officers.

Aadhaar candidates are confirmed with the Verhoeff checksum UIDAI uses, which
keeps false positives on ordinary 12-digit numbers (case IDs, amounts) low.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(number: str) -> bool:
    check = 0
    for i, digit in enumerate(reversed(number)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][int(digit)]]
    return check == 0


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("UPI", re.compile(r"\b[\w.-]{2,64}@(?:ok[a-z]+|ybl|ibl|axl|apl|upi|paytm|airtel|jio|[a-z]{2,10}bank)\b", re.I)),
    ("PAN", re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")),
    ("BANK_ACCOUNT", re.compile(r"(?i)\b(?:a/?c|acct|account)\s*(?:no\.?|number|#)?\s*[:\-]?\s*(\d{9,18})\b")),
    ("AADHAAR", re.compile(r"(?<!\d)([2-9]\d{3})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")),
    ("PHONE", re.compile(r"(?<![\d+])(?:\+91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?!\d)")),
)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def redacted(self) -> bool:
        return bool(self.counts)


def redact(text: str) -> RedactionResult:
    if not text:
        return RedactionResult(text or "")
    counts: Counter[str] = Counter()

    def substitute(label: str):
        def _replace(match: re.Match[str]) -> str:
            if label == "AADHAAR" and not verhoeff_valid("".join(match.groups())):
                return match.group(0)
            if label == "BANK_ACCOUNT":
                counts[label] += 1
                return match.group(0).replace(match.group(1), f"[{label}]")
            counts[label] += 1
            return f"[{label}]"
        return _replace

    for label, pattern in _PATTERNS:
        text = pattern.sub(substitute(label), text)
    return RedactionResult(text, dict(counts))
