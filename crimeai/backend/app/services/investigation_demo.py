"""
Five synthetic cases from five Delhi police stations, in Hindi and English, with the statements, reports and memos
an investigation collects. They carry known contradictions and one stalled investigation, labelled below, so the
evidence and timeline agents can be measured (scripts/evaluate_investigation.py) and demonstrated.
Nothing here describes real people.
"""
from __future__ import annotations

from datetime import datetime, timedelta

IST = timedelta(hours=5, minutes=30)


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    """A wall-clock time in IST on `day`, as UTC."""
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0) - IST


def demo_cases(now: datetime) -> list[dict]:
    a = (now - timedelta(days=24)).replace(hour=0, minute=0, second=0, microsecond=0)
    b, c, d, e = a + timedelta(days=3), a + timedelta(days=6), a + timedelta(days=8), a + timedelta(days=12)

    def day(x: datetime, plus: int = 0) -> str:
        return f"{x + timedelta(days=plus):%d %B %Y}"

    def num(x: datetime, plus: int = 0) -> str:
        return f"{x + timedelta(days=plus):%d/%m/%Y}"

    return [
        {
            "case_number": "DL-INV-2026-001", "district": "Saket", "crime_type": "vehicle_theft", "severity": 2,
            "occurred_at": _at(a, 20), "lat": 28.5286, "lng": 77.2190, "language": "en",
            "fir": (f"On {day(a)} at about 8 PM the complainant's black Pulsar motorcycle DL 5S AB 1234 was stolen from "
                    "the parking near gate 3 of the Select City mall, Saket. The handle lock was broken."),
            "documents": [
                ("witness_statement", "Statement of PW-1, parking guard", _at(a, 11) + timedelta(days=1),
                 f"I saw two young men push a black motorcycle out of the parking at about 8 PM on {day(a)}. "
                 "The pillion rider wore a red helmet."),
                ("cctv_note", "CCTV description, camera 3 at gate 3", _at(a, 15) + timedelta(days=2),
                 f"Camera 3 shows a black motorcycle leaving the parking at 21:04 on {day(a)}, two riders, pillion in a "
                 "red helmet. Camera clock checked against network time."),
                ("seizure_memo", "Seizure memo, Mehrauli", _at(a, 13) + timedelta(days=4),
                 f"Recovered a black Pulsar motorcycle DL 5S AB 1243 abandoned near Mehrauli bus depot on {day(a, 4)}. "
                 "Seized under BNSS s.105 in the presence of two independent witnesses."),
                ("forensic_report", "Fingerprint report", _at(a, 16) + timedelta(days=16),
                 f"Two chance prints were lifted from the fuel tank on {day(a, 5)}. Both are suitable for comparison and "
                 "have been forwarded for NAFIS search."),
            ],
            "expected": {"contradiction:incident_time", "contradiction:vehicle", "gap"},
        },
        {
            "case_number": "DL-INV-2026-002", "district": "Malviya Nagar", "crime_type": "chain_snatching", "severity": 3,
            "occurred_at": _at(b, 19), "lat": 28.5355, "lng": 77.2109, "language": "hi",
            "fir": (f"दिनांक {num(b)} को शाम 7 बजे मालवीय नगर मार्केट के पास मोटरसाइकिल DL 5S AB 1234 पर सवार दो लड़कों ने "
                    "शिकायतकर्ता की सोने की चेन छीन ली और भाग गए।"),
            "documents": [
                ("witness_statement", "गवाह PW-1 का बयान", _at(b, 12) + timedelta(days=1),
                 "मैंने रात 9 बजे दो लड़कों को काली मोटरसाइकिल पर चेन छीनते देखा। पीछे बैठे लड़के ने लाल हेलमेट पहना था।"),
                ("investigation_report", "IO's site visit", _at(b, 17) + timedelta(days=2),
                 f"Site visited on {day(b, 1)}. The motorcycle number in the FIR is the one reported stolen in case "
                 "DL-INV-2026-001 at Saket."),
            ],
            "expected": {"contradiction:incident_time"},
        },
        {
            "case_number": "DL-INV-2026-003", "district": "Hauz Khas", "crime_type": "robbery", "severity": 3,
            "occurred_at": _at(c, 22, 15), "lat": 28.5494, "lng": 77.2001, "language": "en",
            "fir": (f"On {day(c)} at around 10:15 PM two men on a black motorcycle robbed a delivery agent of his phone "
                    "and Rs 6,500 cash near Hauz Khas village. The pillion rider wore a red helmet."),
            "documents": [
                ("witness_statement", "Statement of the delivery agent", _at(c, 10) + timedelta(days=1),
                 "They stopped me at 10:15 PM and took my phone and the Rs 6,500 cash I had collected."),
                ("cctv_note", "CCTV description, Aurobindo Marg", _at(c, 18) + timedelta(days=1),
                 f"A black motorcycle with a pillion rider in a red helmet passes the camera at 22:21 on {day(c)}."),
            ],
            "expected": set(),
        },
        {
            "case_number": "DL-INV-2026-004", "district": "Dwarka", "crime_type": "fraud", "severity": 2,
            "occurred_at": _at(d, 18, 40), "lat": 28.5921, "lng": 77.0460, "language": "hi",
            "fir": (f"दिनांक {num(d)} को शिकायतकर्ता को एक कॉल आया। कॉलर ने KYC अपडेट के नाम पर OTP लिया और "
                    "खाते से ₹12,000 कट गए।"),
            "documents": [
                ("bank_statement", "UPI transaction statement", _at(d, 11) + timedelta(days=1),
                 f"Rs 21,000 was debited on {day(d)} at 18:42 by UPI to a merchant handle; UTR AXN26301229."),
            ],
            "expected": {"contradiction:amount"},
        },
        {
            "case_number": "DL-INV-2026-005", "district": "Rohini", "crime_type": "chain_snatching", "severity": 3,
            "occurred_at": _at(e, 20, 30), "lat": 28.7158, "lng": 77.1137, "language": "en",
            "fir": (f"On {day(e)} at about 8:30 PM two men on a black motorcycle snatched a gold chain near Rohini "
                    "Sector 7 market. The pillion rider wore a red helmet; the number plate was covered."),
            "documents": [
                ("witness_statement", "Statement of PW-1, shopkeeper", _at(e, 12) + timedelta(days=1),
                 "I saw the two men on the motorcycle at 8:30 PM. The rider at the back had a red helmet."),
            ],
            "expected": set(),
        },
    ]
