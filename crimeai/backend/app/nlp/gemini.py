"""
Gemini case brief: an English reading of any FIR, for the officer who does not read its language.

The rules-based reader stays the record (sections, identifiers, links). Gemini adds what rules
cannot: a faithful English translation, a short summary, the modus operandi in plain phrases, the
facts an investigator looks for first, and what the FIR leaves out. Its section suggestions are
checked against the IPC-BNS crosswalk and labelled, never applied to the case.

Only PII-redacted text leaves the deployment: Aadhaar, phone, PAN, bank and UPI numbers are masked
before the request is built, and the instruction forbids reconstructing them. The feature stays off
until GEMINI_API_KEY is set; the endpoints that call it audit every request.
"""
from __future__ import annotations

import base64
import json
import re
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.nlp.legal.bns_crosswalk import IPC_TO_BNS, analyse_sections, governing_code
from app.nlp.multilingual import normalise_digits, normalise_for_legal
from app.nlp.privacy.redaction import redact
from app.schemas.crime import VALID_CRIME_TYPES

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MAX_CHARS = 12_000
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_SECTION = re.compile(r"[^0-9A-Za-z()]")
_WORD = re.compile(r"[a-z]{4,}")
_FILLER = {"with", "from", "under", "that", "which", "into", "their", "section", "offence", "person", "persons",
           "property", "punishment", "committed", "commission", "other", "another", "being"}

_STR = {"type": "STRING"}
_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "english": _STR,
        "summary": _STR,
        "offence": _STR,
        "modus_operandi": {"type": "ARRAY", "items": _STR},
        "facts": {
            "type": "OBJECT",
            "properties": {"when": _STR, "where": _STR, "property": _STR, "weapon": _STR},
        },
        "suggested_sections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"code": _STR, "section": _STR, "reason": _STR},
                "required": ["code", "section", "reason"],
            },
        },
        "missing": {"type": "ARRAY", "items": _STR},
    },
    "required": ["english", "summary", "offence", "modus_operandi", "facts", "suggested_sections", "missing"],
}


# A key that is rate-limited, revoked or out of quota hands the request to the next one.
_FAILOVER_STATUSES = {401, 402, 403, 429, 500, 502, 503, 504}


def _keys() -> list[str]:
    """GEMINI_API_KEY holds one key, or several separated by commas: the first is primary, the rest are backups."""
    return [k.strip() for k in settings.GEMINI_API_KEY.split(",") if k.strip()]


def enabled() -> bool:
    return bool(_keys()) or bool(settings.VERTEX_PROJECT)


_VERTEX_ENDPOINT = "https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"
_METADATA_SA_URL = "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint, not a secret
_vertex_token: dict[str, Any] = {"value": "", "expires": 0.0}


async def _vertex_bearer(client: httpx.AsyncClient) -> str | None:
    """
    An OAuth token for Vertex AI, cached until near expiry: set explicitly, refreshed from a gcloud credentials
    file, or the VM service account's from the metadata server.
    """
    if settings.VERTEX_ACCESS_TOKEN:
        return settings.VERTEX_ACCESS_TOKEN
    if _vertex_token["value"] and _vertex_token["expires"] > time.time() + 60:
        return _vertex_token["value"]
    try:
        if settings.VERTEX_CREDENTIALS_FILE:
            # A few hundred bytes, read once an hour at most: not worth a thread hop.
            creds = json.loads(Path(settings.VERTEX_CREDENTIALS_FILE).read_text(encoding="utf-8"))
            response = await client.post(_OAUTH_TOKEN_URL, timeout=10.0, data={
                "grant_type": "refresh_token", "refresh_token": creds["refresh_token"],
                "client_id": creds["client_id"], "client_secret": creds["client_secret"],
            })
        else:
            response = await client.get(_METADATA_SA_URL, headers={"Metadata-Flavor": "Google"}, timeout=3.0)
        body = response.json() if response.status_code == 200 else {}
    except (httpx.HTTPError, ValueError, OSError, KeyError):
        return None
    if not body.get("access_token"):
        return None
    _vertex_token.update(value=body["access_token"], expires=time.time() + float(body.get("expires_in", 300)))
    return _vertex_token["value"]


async def _post_vertex(client: httpx.AsyncClient, model: str, payload: dict[str, Any]) -> httpx.Response | None:
    token = await _vertex_bearer(client)
    if token is None:
        return None
    location = settings.VERTEX_LOCATION
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    url = _VERTEX_ENDPOINT.format(host=host, project=settings.VERTEX_PROJECT, location=location, model=model)
    return await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})


async def _send(client: httpx.AsyncClient, payload: dict[str, Any], models: tuple[str, ...] = ()) -> httpx.Response:
    """
    For each model in order: every Gemini API key, then Vertex AI; the first answer that is not a quota, auth or
    server failure wins. The caller sees the last failure when nothing answers.
    """
    # A key string is a Gemini API route; None is the Vertex AI route.
    routes: list[str | None] = [*_keys(), *([None] if settings.VERTEX_PROJECT else [])]
    attempts = [(model, route) for model in (models or (settings.GEMINI_MODEL,)) for route in routes]
    last_response: httpx.Response | None = None
    last_error: httpx.HTTPError | None = None
    for model, key in attempts:
        try:
            if key is None:
                response = await _post_vertex(client, model, payload)
                if response is None:
                    continue
            else:
                # In a header, not the URL: query strings end up in proxy and access logs.
                response = await client.post(_ENDPOINT.format(model=model), json=payload, headers={"x-goog-api-key": key})
        except httpx.HTTPError as exc:
            last_error = exc
            continue
        # A revoked or mistyped key answers 400 API_KEY_INVALID: that key is unusable, the request is not.
        if response.status_code not in _FAILOVER_STATUSES and not (
            response.status_code == 400 and "API_KEY_INVALID" in response.text
        ):
            return response
        last_response = response
    if last_response is not None:
        return last_response
    raise last_error or httpx.HTTPError("no API key or Vertex project configured")


def _instruction(code: str) -> str:
    regime = (
        "The incident is on or after 1 July 2024, so cite Bharatiya Nyaya Sanhita (BNS) sections."
        if code == "BNS" else
        "The incident is before 1 July 2024, so cite Indian Penal Code (IPC) sections."
    )
    return (
        "You help Indian police analysts read First Information Reports (FIRs) written in any Indian language. "
        "Personal identifiers are masked as [PHONE], [AADHAAR], [UPI], [BANK_ACCOUNT] and similar: keep the masks "
        "and never guess what they hide. Translate faithfully and add no facts. Do not name, profile or speculate "
        f"about suspects beyond what the FIR states. {regime} Suggest at most four sections, each with a one-line "
        "reason tied to the text, and add the IT Act only when the text supports it. List up to five details an "
        "investigator needs that the FIR does not give. Answer in English: summary under 45 words, each modus "
        "operandi item under 8 words, facts as short phrases or an empty string when the FIR is silent."
    )


def _strings(value: Any, limit: int) -> list[str]:
    items = value if isinstance(value, list) else []
    return [str(v).strip() for v in items if str(v).strip()][:limit]


def _norm(section: str) -> str:
    return _SECTION.sub("", section).upper()


def _titles() -> dict[tuple[str, str], str]:
    """Official titles the crosswalk knows, by (code, section)."""
    known: dict[tuple[str, str], str] = {}
    for ipc, (bns, title, _) in IPC_TO_BNS.items():
        known.setdefault(("IPC", _norm(ipc)), title)
        known.setdefault(("BNS", _norm(bns)), title)
    return known


_TITLES = _titles()


def _stems(text: str) -> set[str]:
    return {w[:5] for w in _WORD.findall(text.lower()) if w not in _FILLER}


def _check_sections(suggested: list[dict], text: str, incident_date: date | datetime | None, code: str) -> list[dict]:
    """
    Label each suggestion against the law and the FIR: a section from the code that did not govern the
    incident date, one whose stated reason shares no word with its official title (a model confusing
    section numbers), one the FIR already cites, or a new suggestion to check.
    """
    legal = analyse_sections(normalise_for_legal(text), incident_date)
    cited = {_norm(m["bns"]) for m in legal["mapped"] if m.get("bns")} | {
        _norm(m["ipc"]) for m in legal["mapped"] if m.get("ipc")
    }
    checked = []
    for item in suggested[:4]:
        if not isinstance(item, dict) or not str(item.get("section", "")).strip():
            continue
        item_code = str(item.get("code", "")).strip().upper() or code
        section = str(item["section"]).strip()
        reason = str(item.get("reason", "")).strip()
        title = _TITLES.get((item_code, _norm(section)))
        if item_code in {"IPC", "BNS"} and item_code != code:
            status = "wrong_code"
        elif _norm(section) in cited:
            status = "cited_in_fir"
        elif title and not _stems(title) & _stems(reason):
            status = "title_differs"
        else:
            status = "new"
        checked.append({"code": item_code, "section": section, "reason": reason, "official_title": title,
                        "status": status})
    return checked


def _parse(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(_FENCE.sub("", raw.strip()))
    except json.JSONDecodeError as exc:
        raise ExternalServiceError("Gemini returned a reply that is not JSON") from exc
    if not isinstance(data, dict):
        raise ExternalServiceError("Gemini returned an unexpected reply")
    return data


async def case_brief(
    text: str, incident_date: date | datetime | None = None, *, client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Redact, ask Gemini for a structured English brief, and check its section suggestions."""
    if not enabled():
        raise ExternalServiceError("Gemini is not configured: set GEMINI_API_KEY")
    redaction = redact(normalise_digits(text or ""))
    sent = redaction.text[:_MAX_CHARS]
    code = governing_code(incident_date)
    payload = {
        "systemInstruction": {"parts": [{"text": _instruction(code)}]},
        "contents": [{"role": "user", "parts": [{"text": f"FIR text:\n{sent}"}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA,
        },
    }
    owned = client is None
    client = client or httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS)
    try:
        response = await _send(client, payload)
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Gemini could not be reached", detail=type(exc).__name__) from exc
    finally:
        if owned:
            await client.aclose()

    if response.status_code != 200:
        try:
            reason = response.json().get("error", {}).get("message")
        except ValueError:
            reason = None
        raise ExternalServiceError(f"Gemini returned HTTP {response.status_code}", detail=reason)
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        blocked = (body.get("promptFeedback") or {}).get("blockReason")
        raise ExternalServiceError("Gemini returned no answer", detail=blocked)
    parts = (candidates[0].get("content") or {}).get("parts") or []
    data = _parse("".join(p.get("text", "") for p in parts if not p.get("thought")))

    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    return {
        "model": settings.GEMINI_MODEL,
        "generated_at": datetime.now(UTC).isoformat(),
        "governing_code": code,
        "redactions": dict(redaction.counts),
        "chars_sent": len(sent),
        "english": str(data.get("english", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "offence": str(data.get("offence", "")).strip(),
        "modus_operandi": _strings(data.get("modus_operandi"), 5),
        "facts": {k: str(facts.get(k, "") or "").strip() for k in ("when", "where", "property", "weapon")},
        "suggested_sections": _check_sections(data.get("suggested_sections") or [], text, incident_date, code),
        "missing": _strings(data.get("missing"), 5),
    }


_OCR_TYPES = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "application/pdf"}
_OCR_INSTRUCTION = (
    "You are an OCR engine for Indian police First Information Report (FIR) forms. Transcribe ALL text in the "
    "image exactly as written, printed and handwritten. A single FIR often mixes scripts and languages, for "
    "example an English printed form filled in by hand in Bengali, Hindi or English, or a Bengali narrative with "
    "English names, sections and numbers: write every word in the script it is written in (Bengali in Bengali "
    "script, Devanagari in Devanagari, Latin in Latin) and never transliterate or translate. Bengali and Assamese "
    "share a script; keep the letters as written. Copy numbers, dates, section numbers (e.g. 341/325/354B), "
    "vehicle and phone numbers digit by digit, keeping Bengali or Devanagari digits as written. Do not guess: "
    "never fill a blank field, and write a word you cannot read as [?]. Keep the reading order of the form: "
    "field label, then the value written next to it, one field per line; then the complaint narrative in its "
    "own paragraphs. Ignore stamps, signatures and watermarks unless they contain readable text. Return only the "
    "transcription."
)


async def read_document(data: bytes, mime_type: str, *, client: httpx.AsyncClient | None = None) -> str:
    """Transcribe a scanned or photographed FIR, handwriting included, in its own script."""
    if not enabled():
        raise ExternalServiceError("Gemini is not configured: set GEMINI_API_KEY")
    if mime_type not in _OCR_TYPES:
        raise ExternalServiceError(f"Unsupported file type for handwriting OCR: {mime_type}")
    payload = {
        "systemInstruction": {"parts": [{"text": _OCR_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode()}},
            {"text": "Transcribe this FIR."},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192, "mediaResolution": "MEDIA_RESOLUTION_HIGH"},
    }
    owned = client is None
    client = client or httpx.AsyncClient(timeout=max(settings.GEMINI_TIMEOUT_SECONDS, 90.0))
    try:
        response = await _send(client, payload, (settings.GEMINI_OCR_MODEL, settings.GEMINI_MODEL))
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Handwriting OCR could not be reached", detail=type(exc).__name__) from exc
    finally:
        if owned:
            await client.aclose()
    if response.status_code != 200:
        try:
            reason = response.json().get("error", {}).get("message")
        except ValueError:
            reason = None
        raise ExternalServiceError(f"Handwriting OCR returned HTTP {response.status_code}", detail=reason)
    candidates = response.json().get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    text = _FENCE.sub("", text).strip()
    if not text:
        raise ExternalServiceError("No text could be read from this image")
    return text


# The crime types a case may carry; "other" last so it reads as the fallback.
CRIME_TYPES = (*sorted(VALID_CRIME_TYPES - {"other"}), "other")
_CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "crime_type": {"type": "STRING", "enum": list(CRIME_TYPES)},
        "confidence": {"type": "NUMBER"},
        "severity": {"type": "INTEGER"},
        "reasoning": _STR,
        "people": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": _STR,
                    "role": {"type": "STRING", "enum": ["complainant", "victim", "accused", "suspect", "witness", "other"]},
                    "detail": _STR,
                },
                "required": ["name", "role"],
            },
        },
        "timeline": {"type": "ARRAY", "items": _STR},
        "motive": _STR,
        "relationship": _STR,
        "premeditated": {"type": "BOOLEAN"},
        "violence": {"type": "BOOLEAN"},
        "injury": {"type": "BOOLEAN"},
        "weapons": {"type": "ARRAY", "items": _STR},
        "red_flags": {"type": "ARRAY", "items": _STR},
        "place": _STR,
        "district": _STR,
        "city": _STR,
        "latitude": {"type": "NUMBER"},
        "longitude": {"type": "NUMBER"},
    },
    "required": ["crime_type", "confidence", "severity", "reasoning", "people", "timeline", "motive",
                 "relationship", "premeditated", "violence", "injury", "weapons", "red_flags", "place",
                 "district", "city", "latitude", "longitude"],
}
_CONTEXT_INSTRUCTION = (
    "You read Indian police FIRs in any Indian language and explain what happened, in English. Personal "
    "identifiers are masked as [PHONE], [AADHAAR], [UPI], [BANK_ACCOUNT] and similar: keep the masks and never "
    "guess them. Use only what the FIR states; add no facts and do not profile anyone. Pick the one crime_type "
    "that best fits the whole narrative, reading negation, sequence and intent rather than keywords (online or "
    "UPI cheating is cybercrime, rash driving is traffic_violation); confidence is 0 to 1. severity is 1 (minor) to 5 (grave, life threatening). "
    "reasoning is one sentence under 30 words. people lists each named or described person with their role and "
    "a short detail. timeline is up to six short events in order. motive and relationship (between accused and "
    "victim) are short phrases, or an empty string when the FIR is silent. red_flags are up to four investigative "
    "signals the text actually supports, such as an organised gang, a repeat pattern, an insider or a threat to a "
    "witness. place, district and city are where the offence happened, in English (the police station's area when "
    "nothing else is given), or an empty string; district is the district's full official name, never an "
    "abbreviation (North 24 Parganas, not 24 Pgs (N)). latitude and longitude are the "
    "approximate coordinates of that place in India, or 0 when it cannot be placed."
)


async def understand(text: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Contextual reading of an FIR: who did what to whom, in what order, why, and how serious it is."""
    if not enabled():
        raise ExternalServiceError("Gemini is not configured: set GEMINI_API_KEY")
    redaction = redact(normalise_digits(text or ""))
    payload = {
        "systemInstruction": {"parts": [{"text": _CONTEXT_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": f"FIR text:\n{redaction.text[:_MAX_CHARS]}"}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "responseSchema": _CONTEXT_SCHEMA,
        },
    }
    owned = client is None
    client = client or httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS)
    try:
        response = await _send(client, payload)
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Context model could not be reached", detail=type(exc).__name__) from exc
    finally:
        if owned:
            await client.aclose()
    if response.status_code != 200:
        raise ExternalServiceError(f"Context model returned HTTP {response.status_code}")
    candidates = response.json().get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    data = _parse("".join(p.get("text", "") for p in parts if not p.get("thought")))

    people = [
        {"name": str(p.get("name", "")).strip(), "role": str(p.get("role") or "other"),
         "detail": str(p.get("detail") or "").strip()}
        for p in (data.get("people") or []) if isinstance(p, dict) and str(p.get("name", "")).strip()
    ][:8]
    return {
        "crime_type": data.get("crime_type") if data.get("crime_type") in CRIME_TYPES else "other",
        "confidence": round(min(max(float(data.get("confidence") or 0), 0.0), 1.0), 2),
        "severity": min(max(int(data.get("severity") or 1), 1), 5),
        "reasoning": str(data.get("reasoning", "")).strip(),
        "people": people,
        "timeline": _strings(data.get("timeline"), 6),
        "motive": str(data.get("motive") or "").strip(),
        "relationship": str(data.get("relationship") or "").strip(),
        "premeditated": bool(data.get("premeditated")),
        "violence": bool(data.get("violence")),
        "injury": bool(data.get("injury")),
        "weapons": _strings(data.get("weapons"), 5),
        "red_flags": _strings(data.get("red_flags"), 4),
        "place": str(data.get("place") or "").strip(),
        "district": str(data.get("district") or "").strip(),
        "city": str(data.get("city") or "").strip(),
        "latitude": _coordinate(data.get("latitude"), 6.0, 37.5),
        "longitude": _coordinate(data.get("longitude"), 68.0, 97.5),
    }


def _coordinate(value: Any, low: float, high: float) -> float | None:
    """A coordinate inside India's bounding box, or None: a model's 0 or a point abroad is no location."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 5) if low <= number <= high else None


_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
                "audio/aac", "audio/flac", "audio/x-m4a", "audio/m4a"}
_TRANSCRIBE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "transcript": _STR,
        "statement": _STR,
        "languages": {"type": "ARRAY", "items": _STR},
    },
    "required": ["transcript", "statement", "languages"],
}
_TRANSCRIBE_INSTRUCTION = (
    "You transcribe a complainant speaking their complaint to an Indian police officer. Speakers often mix "
    "languages in one sentence (Hindi, Bengali, English, Marathi, Tamil or any other Indian language). "
    "transcript: every word exactly as spoken, each word in the script of the language it was spoken in "
    "(Hindi in Devanagari, Bengali in Bengali script, English in Latin), with punctuation; never translate. "
    "statement: the same account written as a clean first-person complaint for the FIR, in the same languages and "
    "scripts, keeping every fact (names, places, times, dates, amounts, vehicle, phone and account numbers digit "
    "by digit) and dropping only fillers, repetitions and false starts. Add nothing that was not said. Write a "
    "word you cannot make out as [?]. languages: the languages heard, in English."
)


async def transcribe(data: bytes, mime_type: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """A spoken complaint, in any mix of Indian languages, as a verbatim transcript and a clean FIR statement."""
    if not enabled():
        raise ExternalServiceError("Gemini is not configured: set GEMINI_API_KEY")
    mime = mime_type.split(";")[0].strip().lower()
    if mime not in _AUDIO_TYPES:
        raise ExternalServiceError(f"Unsupported audio type: {mime_type}")
    payload = {
        "systemInstruction": {"parts": [{"text": _TRANSCRIBE_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}},
            {"text": "Transcribe this complaint."},
        ]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": _TRANSCRIBE_SCHEMA,
            # Speech needs listening, not reasoning: minimal thinking halves the wait with the same transcript.
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }
    owned = client is None
    client = client or httpx.AsyncClient(timeout=max(settings.GEMINI_TIMEOUT_SECONDS, 90.0))
    try:
        response = await _send(client, payload, (settings.GEMINI_OCR_MODEL, settings.GEMINI_MODEL))
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Speech reader could not be reached", detail=type(exc).__name__) from exc
    finally:
        if owned:
            await client.aclose()
    if response.status_code != 200:
        raise ExternalServiceError(f"Speech reader returned HTTP {response.status_code}")
    candidates = response.json().get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    result = _parse("".join(p.get("text", "") for p in parts if not p.get("thought")))
    transcript = str(result.get("transcript") or "").strip()
    statement = str(result.get("statement") or "").strip() or transcript
    if not statement:
        raise ExternalServiceError("No speech could be made out in this recording")
    return {"transcript": transcript, "statement": statement, "languages": _strings(result.get("languages"), 5)}
