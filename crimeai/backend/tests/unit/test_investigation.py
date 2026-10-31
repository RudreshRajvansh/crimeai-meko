"""Evidence and timeline agents: what they read from each document, and when they raise a finding."""
from datetime import UTC, datetime

from app.nlp.privacy.redaction import redact
from app.services.investigation import Doc, dates_in, evidence_agent, investigate, timeline_agent, times_in
from app.services.investigation_demo import demo_cases


def test_times_in_english_hindi_and_hinglish():
    assert times_in("stolen at about 8 PM") == [20 * 60]
    assert times_in("leaving the parking at 21:04 hrs") == [21 * 60 + 4]
    assert times_in("रात 9 बजे दो लड़के") == [21 * 60]
    assert times_in("shaam 7 baje chain cheen li") == [19 * 60]
    assert times_in("raat 2 baje") == [2 * 60], "small hours stay in the morning"
    assert times_in("report dated 14.10.2026") == [], "a dotted date is not a time"


def test_dates_in_numeric_and_named_months():
    assert [d.isoformat() for d in dates_in("on 10 October 2026 at night", 2026)] == ["2026-10-10"]
    assert [d.isoformat() for d in dates_in("घटना 11 अक्टूबर को हुई", 2026)] == ["2026-10-11"]
    assert [d.isoformat() for d in dates_in("October 12, 2026 and 13/10/2026", 2026)] == ["2026-10-12", "2026-10-13"]


def _docs(*items):
    return [Doc(str(i), title, t, text) for i, (title, t, text) in enumerate(items)]


def test_time_contradiction_cites_both_sources():
    _, findings = evidence_agent(_docs(
        ("Statement of PW-1", "witness_statement", "I saw them take the bike at 8 PM."),
        ("CCTV note", "cctv_note", "The motorcycle leaves the parking at 21:04."),
    ), 2026)
    (f,) = findings
    assert f["subject"] == "incident_time" and f["difference"] == "1 h 4 min"
    assert {c["doc_title"] for c in f["claims"]} == {"Statement of PW-1", "CCTV note"}
    assert all(c["quote"] for c in f["claims"])


def test_small_time_differences_are_not_contradictions():
    _, findings = evidence_agent(_docs(
        ("FIR", "fir", "Robbed at around 10:15 PM."), ("CCTV", "cctv_note", "Passes the camera at 22:21."),
    ), 2026)
    assert findings == []


def test_transposed_vehicle_number_is_flagged_but_two_vehicles_in_one_document_are_not():
    _, findings = evidence_agent(_docs(
        ("FIR", "fir", "Motorcycle DL 5S AB 1234 was stolen."),
        ("Seizure memo", "seizure_memo", "Recovered motorcycle DL 5S AB 1243 near the depot."),
    ), 2026)
    assert [f["difference"] for f in findings] == ["two neighbouring characters swapped"]
    _, findings = evidence_agent(_docs(
        ("FIR", "fir", "Motorcycles DL 5S AB 1234 and DL 5S AB 1243 were both seen."),
        ("Memo", "seizure_memo", "Recovered DL 5S AB 1243."),
    ), 2026)
    assert findings == []


def test_amount_contradiction_and_redaction_keeps_amounts():
    text = redact("Caller from 9810012345 took the OTP and Rs 12,000 was debited.").text
    assert "9810012345" not in text
    _, findings = evidence_agent(_docs(("FIR", "fir", text), ("Bank", "bank_statement", "Rs 21,000 was debited by UPI.")), 2026)
    assert [(f["subject"], f["difference"]) for f in findings] == [("amount", "Rs 9,000")]


def test_timeline_orders_sources_and_flags_a_stalled_week():
    occurred = datetime(2026, 10, 1, 14, tzinfo=UTC)
    docs = [Doc("a", "Statement", "witness_statement", "Seen on 2 October 2026.", datetime(2026, 10, 2, tzinfo=UTC)),
            Doc("b", "Forensic report", "forensic_report", "Prints compared.", datetime(2026, 10, 20, tzinfo=UTC))]
    events, gaps = timeline_agent({"occurred_at": occurred}, docs, [{"captured_at": "2026-10-03T10:00:00+00:00",
                                                                     "provision": "105", "sid": "1234"}], 2026)
    assert [e["kind"] for e in events][:2] == ["incident", "document"]
    assert [g["difference"] for g in gaps] == ["17 days"]


def test_labelled_demo_cases_are_all_found_with_no_false_alarms():
    for case in demo_cases(datetime.now(UTC)):
        docs = [Doc("fir", "FIR", "fir", redact(case["fir"]).text)]
        docs += [Doc(f"d{i}", t, k, redact(x).text, at) for i, (k, t, at, x) in enumerate(case["documents"])]
        findings = investigate({"occurred_at": case["occurred_at"]}, docs, [])["findings"]
        found = {f"contradiction:{f['subject']}" if f["kind"] == "contradiction" else f["kind"] for f in findings}
        assert found == case["expected"], case["case_number"]
