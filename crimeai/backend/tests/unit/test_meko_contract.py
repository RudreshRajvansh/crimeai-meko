"""The Meko memory contract: fingerprints, phrasing that survives rewording, and links computed from recall only."""
import pytest

from app.meko import contract
from app.meko.client import context_buckets, parse_tool_result, to_hits

U1, P1, H = "UPI-AAAAAAAAAA", "PH-BBBBBBBBBB", "PH-CCCCCCCCCC"


def item(ref: str, text: str, score: float = 0.8) -> dict:
    return {"ref": ref, "id": ref.lower(), "text": text, "score": score, "datapack": "grid", "parsed": contract.parse(text)}


def test_fingerprints_are_stable_across_formats_and_never_raw():
    a = contract.grid_identifiers("caller 90000 11223 asked for UPI parcelfee.clear@okdemo")
    b = contract.grid_identifiers("call from +91-9000011223 to PARCELFEE.CLEAR@OKDEMO")
    assert {i.token for i in a} == {i.token for i in b}
    for ident in a:
        assert contract.TOKEN_RE.fullmatch(ident.token)
        assert "11223" not in ident.token and "parcelfee" not in ident.token
    assert {i.kind for i in a} == {"phone", "upi"}


def test_mo_tags_from_any_language():
    assert "courier-customs" in contract.mo_tags("उनका पार्सल कस्टम में रुका है, UPI से भुगतान")
    assert contract.mo_tags("Usne GPay se payment kiya, parcel customs mein ruka") == ["courier-customs", "upi"]
    assert "vehicle-lifting" in contract.mo_tags("stolen", "vehicle_theft")


def test_parse_survives_rewording():
    p = contract.parse(f"The UPI handle {U1} and phone {P1} were used in case GGM:GGM-2026-0412 in Gurugram; "
                       "courier-customs fraud paid by upi.")
    assert p.kind == "sighting" and p.tokens == {U1, P1} and p.refs == {"GGM:GGM-2026-0412"}
    assert p.tags == {"courier-customs", "upi"}


def test_builders_round_trip():
    s = contract.series_memory("SR-DLP-01", ["courier-customs"], ["GGM:GGM-2026-0412", "NOI:NOI-2026-0377"], [U1],
                               "Gurugram Cyber PS", "ring rotates SIMs", "police officer, Delhi Police", "2026-10-31")
    ps = contract.parse(s)
    assert ps.kind == "series" and ps.series_ids == {"SR-DLP-01"} and ps.lead == "Gurugram Cyber PS"
    assert ps.note == "ring rotates SIMs" and ps.refs == {"GGM:GGM-2026-0412", "NOI:NOI-2026-0377"}
    pe = contract.parse(contract.exclusion_memory(H, "public customer care", "officer", "2026-10-31"))
    assert pe.kind == "exclusion" and pe.tokens == {H}
    sighting = contract.sighting_memory("DLP:FIR/101/2026", "Dwarka", "2026-10-31", "fraud", ["courier-customs"], [U1])
    assert contract.parse(sighting).refs == {"DLP:FIR/101/2026"}


def test_links_exclusions_and_series_come_only_from_recall():
    items = [
        item("M1", contract.sighting_memory("GGM:GGM-2026-0412", "Sector 29", "2026-10-12", "fraud", ["courier-customs", "upi"], [U1, P1])),
        item("M2", contract.sighting_memory("NOI:NOI-2026-0391", "Sector 18", "2026-10-26", "cybercrime", ["kyc-otp"], [H])),
        item("M3", contract.exclusion_memory(H, "public customer care", "officer", "2026-10-31")),
        item("M4", contract.series_memory("SR-DLP-01", ["courier-customs"], ["GGM:GGM-2026-0300"], ["UPI-DDDDDDDDDD"],
                                          "Gurugram Cyber PS", "", "officer", "2026-10-31")),
        item("M5", contract.sighting_memory("NOI:NOI-2026-0500", "Sector 62", "2026-10-29", "fraud", ["courier-customs"], ["UPI-EEEEEEEEEE"])),
    ]
    a = contract.analyse_recall(None, {U1, P1, H}, ["courier-customs", "upi"], items)
    assert [link["ref"] for link in a["links"]] == ["GGM:GGM-2026-0412"]
    assert a["links"][0]["tokens"] == sorted([U1, P1])
    assert a["excluded"] == [{"token": H, "ref": "M3", "memory_id": "m3"}]
    assert a["series"][0]["series_id"] == "SR-DLP-01" and a["series"][0]["basis"] == ["method"]
    assert [s["ref"] for s in a["similar"]] == ["NOI:NOI-2026-0500"]
    assert contract.analyse_recall(None, {U1}, ["upi"], items[4:])["similar"] == [], "payment tags never link"


def test_cases_in_a_matched_series_are_not_proposed_again():
    sighting = item("M1", contract.sighting_memory("GGM:GGM-2026-0412", None, "2026-10-12", "fraud", ["courier-customs"], [U1]))
    series = item("M2", contract.series_memory("SR-DLP-01", ["courier-customs"], ["GGM:GGM-2026-0412"], [U1],
                                               "Gurugram Cyber PS", "", "officer", "2026-10-31"))
    a = contract.analyse_recall(None, {U1}, ["courier-customs"], [sighting, series])
    assert a["links"] == [] and a["series"][0]["refs"] == ["GGM:GGM-2026-0412"]
    b = contract.analyse_recall(None, {"UPI-ZZZZZZZZZZ"}, ["courier-customs"], [sighting, series])
    assert b["similar"] == [] and b["series"][0]["basis"] == ["method"], "method-only members fold into the series"


def test_response_shapes():
    assert [h.id for h in to_hits({"results": [{"id": "a", "memory": "x", "score": 0.4}]})] == ["a"]
    assert [h.text for h in to_hits([{"memory_id": "b", "text": "y"}])] == ["y"]
    b = context_buckets({"memory": {"status": "ok", "results": [{"id": "1", "memory": "m"}]},
                         "knowledge_base": [{"id": "k", "chunk": "sop"}], "conversation": {"results": []}})
    assert len(b["memory"]["hits"]) == 1 and b["knowledge_base"]["hits"][0].text == "sop"


class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Res:
    def __init__(self, text, is_error=False, structured=None):
        self.content = [_Text(text)]
        self.isError = is_error
        self.structuredContent = structured


def test_parse_tool_result_errors_and_json():
    assert parse_tool_result(_Res('{"results": []}')) == ({"results": []}, None)
    assert parse_tool_result(_Res("boom", is_error=True))[1] == "boom"
    assert parse_tool_result(_Res('{"detail": "datapack not found"}'))[1] == "datapack not found"
    assert parse_tool_result(_Res("plain", structured={"ok": 1})) == ({"ok": 1}, None)


async def test_a_meko_failure_mid_run_becomes_a_meko_error(monkeypatch):
    """A 502 from Meko after the session opened cancels the pending calls; callers get a MekoError, not a crash."""
    from contextlib import asynccontextmanager

    import anyio
    import httpx
    import mcp
    import mcp.client.streamable_http as transport

    from app.core.config import settings
    from app.meko import client

    @asynccontextmanager
    async def failing_transport(*_args, **_kwargs):
        async with anyio.create_task_group() as tg:
            async def post_writer():
                await anyio.sleep(0.05)
                request = httpx.Request("POST", "https://mcp.test/mcp")
                raise httpx.HTTPStatusError("502 Bad Gateway", request=request, response=httpx.Response(502, request=request))
            tg.start_soon(post_writer)
            yield None, None, None

    class Session:
        def __init__(self, *_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, *_):
            await anyio.sleep(5)

    monkeypatch.setattr(settings, "MEKO_API_KEY", "test")
    monkeypatch.setattr(transport, "streamablehttp_client", failing_transport)
    monkeypatch.setattr(mcp, "ClientSession", Session)
    with pytest.raises(client.MekoError) as caught:
        async with client.open_run({"grid": "dp-grid"}, "linker") as run:
            await run.memory_search("linker", "grid", "PH-0000000000")
    assert "connection dropped" in str(caught.value) and "502" in str(caught.value)
    assert caught.value.run.calls[-1]["tool"] == "session" and not caught.value.run.calls[-1]["ok"]
