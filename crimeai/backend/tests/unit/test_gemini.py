"""Gemini case brief: what leaves the deployment, and how its section suggestions are labelled."""
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.nlp import gemini

FIR = (
    "दिनांक 12/09/2025 को लाजपत नगर में शिकायतकर्ता का मोबाइल चोरी हुआ। आरोपी ने 9876543210 से फोन किया "
    "और 5,000 रुपये refund.help@okaxis पर मांगे। धारा 303(2) BNS के तहत मामला दर्ज।"
)
AFTER_BNS = datetime(2025, 9, 12, tzinfo=UTC)


def _reply(payload: dict, fenced: bool = False) -> dict:
    text = json.dumps(payload)
    return {"candidates": [{"content": {"parts": [{"text": f"```json\n{text}\n```" if fenced else text}]}}]}


BRIEF = {
    "english": "On 12/09/2025 the complainant's mobile was stolen in Lajpat Nagar...",
    "summary": "Mobile theft followed by a payment demand to a UPI ID.",
    "offence": "Theft and extortion",
    "modus_operandi": ["phone theft", "payment demand by call", "", "UPI collection"],
    "facts": {"when": "12/09/2025", "where": "Lajpat Nagar", "property": "mobile phone", "weapon": None},
    "suggested_sections": [
        {"code": "BNS", "section": "303(2)", "reason": "theft of movable property"},
        {"code": "IPC", "section": "379", "reason": "theft"},
        {"code": "BNS", "section": "308(2)", "reason": "extortion of money by threat"},
        {"code": "BNS", "section": "324(4)", "reason": "two persons acting with common intention"},
    ],
    "missing": ["time of theft", "phone IMEI"],
}


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-123")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")  # no real Vertex calls from a developer's .env


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_only_redacted_text_is_sent_and_the_key_stays_out_of_the_url(key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=_reply(BRIEF))

    async with _client(handler) as client:
        brief = await gemini.case_brief(FIR, AFTER_BNS, client=client)

    assert seen["url"].endswith("/models/gemini-test:generateContent")
    assert "test-key-123" not in seen["url"] and seen["key"] == "test-key-123"
    sent = json.loads(seen["body"])
    text = sent["contents"][0]["parts"][0]["text"]
    assert "9876543210" not in text and "refund.help@okaxis" not in text
    assert "[PHONE]" in text
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert "Bharatiya Nyaya Sanhita" in sent["systemInstruction"]["parts"][0]["text"]
    assert brief["redactions"].get("PHONE") == 1 and brief["chars_sent"] == len(text) - len("FIR text:\n")


async def test_sections_are_checked_against_the_fir_and_the_governing_code(key):
    async with _client(lambda r: httpx.Response(200, json=_reply(BRIEF, fenced=True))) as client:
        brief = await gemini.case_brief(FIR, AFTER_BNS, client=client)

    status = {s["section"]: s["status"] for s in brief["suggested_sections"]}
    assert status == {"303(2)": "cited_in_fir", "379": "wrong_code", "308(2)": "new",
                      # 324(4) is mischief, not common intention (that is 3(5)): the model mixed up numbers.
                      "324(4)": "title_differs"}
    titles = {s["section"]: s["official_title"] for s in brief["suggested_sections"]}
    assert titles["324(4)"] == "Mischief causing damage" and titles["308(2)"] == "Extortion"
    assert brief["modus_operandi"] == ["phone theft", "payment demand by call", "UPI collection"]
    assert brief["facts"]["weapon"] == "" and brief["governing_code"] == "BNS"
    assert brief["model"] == "gemini-test"


async def test_switched_off_without_a_key_or_vertex_project(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")
    assert not gemini.enabled()
    with pytest.raises(ExternalServiceError):
        await gemini.case_brief(FIR, AFTER_BNS)


async def test_upstream_errors_surface_as_upstream_errors(key):
    error = {"error": {"message": "API key not valid"}}
    async with _client(lambda r: httpx.Response(400, json=error)) as client:
        with pytest.raises(ExternalServiceError) as caught:
            await gemini.case_brief(FIR, AFTER_BNS, client=client)
    assert caught.value.detail == "API key not valid"

    async with _client(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})) as client:
        with pytest.raises(ExternalServiceError):
            await gemini.case_brief(FIR, AFTER_BNS, client=client)

    reply = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
    async with _client(lambda r: httpx.Response(200, json=reply)) as client:
        with pytest.raises(ExternalServiceError):
            await gemini.case_brief(FIR, AFTER_BNS, client=client)


async def test_a_rate_limited_key_hands_over_to_the_backup(monkeypatch):
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "primary-key, backup-key")
    used = []

    def handler(request: httpx.Request) -> httpx.Response:
        used.append(request.headers.get("x-goog-api-key"))
        if used[-1] == "primary-key":
            return httpx.Response(429, json={"error": {"message": "quota"}})
        return httpx.Response(200, json=_reply(BRIEF))

    async with _client(handler) as client:
        brief = await gemini.case_brief(FIR, AFTER_BNS, client=client)

    assert used == ["primary-key", "backup-key"] and brief["summary"]


async def test_a_bad_request_is_not_retried_on_other_keys(monkeypatch):
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "primary-key,backup-key")
    used = []

    def handler(request: httpx.Request) -> httpx.Response:
        used.append(request.headers.get("x-goog-api-key"))
        return httpx.Response(400, json={"error": {"message": "bad"}})

    async with _client(handler) as client:
        with pytest.raises(ExternalServiceError):
            await gemini.case_brief(FIR, AFTER_BNS, client=client)

    assert used == ["primary-key"]


async def test_speech_is_sent_as_audio_and_comes_back_as_a_statement(key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply({
            "transcript": "उम्म मेरा फोन चोरी हो गया", "statement": "मेरा फोन चोरी हो गया।", "languages": ["Hindi"],
        }))

    async with _client(handler) as client:
        result = await gemini.transcribe(b"audio-bytes", "audio/webm;codecs=opus", client=client)

    assert seen["body"]["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "audio/webm"
    assert result == {"transcript": "उम्म मेरा फोन चोरी हो गया", "statement": "मेरा फोन चोरी हो गया।", "languages": ["Hindi"]}


async def test_speech_rejects_files_that_are_not_audio(key):
    with pytest.raises(ExternalServiceError):
        await gemini.transcribe(b"x", "application/pdf")


async def test_vertex_ai_answers_when_every_api_key_is_out_of_credit(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "spent-key")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "demo-project")
    monkeypatch.setattr(settings, "VERTEX_ACCESS_TOKEN", "vertex-token")
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(402, json={"error": {"message": "prepayment credits are depleted"}})
        assert request.headers["authorization"] == "Bearer vertex-token"
        assert "/projects/demo-project/locations/global/publishers/google/models/" in request.url.path
        return httpx.Response(200, json=_reply(BRIEF))

    async with _client(handler) as client:
        brief = await gemini.case_brief(FIR, AFTER_BNS, client=client)

    assert hosts == ["generativelanguage.googleapis.com", "aiplatform.googleapis.com"] and brief["summary"]
