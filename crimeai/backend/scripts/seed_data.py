#!/usr/bin/env python3
"""
Seed a development database with realistic, patterned data.

  python scripts/seed_data.py [--force] [--crimes 3000]

Creates one user per role, ~18 months of Delhi incidents with real temporal
patterns, a planted cross-station chain-snatching series, custody cases close
to their chargesheet deadline, and FIRs citing IPC and BNS sections (including
a deliberately wrong one) so every feature has something to show.

Passwords come from SEED_PASSWORD, or are generated and printed once.
Refuses to run against production.
"""
import argparse
import asyncio
import os
import random
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.crime import Crime
from app.models.fir import FIRReport
from app.models.user import User
from app.nlp.lexicons import CRIME_TERMS

RNG = random.Random(2024)

DISTRICTS = {
    "Connaught Place": (28.6315, 77.2167),
    "Karol Bagh": (28.6525, 77.1900),
    "Rohini": (28.7409, 77.0678),
    "Dwarka": (28.5921, 77.0460),
    "Saket": (28.5245, 77.2066),
    "Lajpat Nagar": (28.5674, 77.2430),
    "Defence Colony": (28.5730, 77.2320),
    "Janakpuri": (28.6270, 77.0837),
    "Shahdara": (28.6757, 77.2900),
}

LANDMARKS = {
    "Connaught Place": ["Palika Bazaar", "Rajiv Chowk metro gate 7", "Janpath market", "Inner Circle Block E", "Shivaji Stadium bus stand"],
    "Karol Bagh": ["Ghaffar Market", "Ajmal Khan Road", "Tank Road", "Pusa Road crossing", "Beadon Pura"],
    "Rohini": ["Sector 7 market", "Rithala metro", "Japanese Park", "Sector 24 DDA flats", "Adventure Island"],
    "Dwarka": ["Sector 10 metro", "Sector 6 market", "Dwarka Mor", "Sector 12 Venkateshwar complex", "Sector 21 metro"],
    "Saket": ["Select Citywalk", "Saket metro", "PVR Anupam complex", "Press Enclave Road", "Max hospital gate"],
    "Lajpat Nagar": ["Central Market", "Amar Colony", "Moolchand flyover", "Lajpat Nagar metro", "Double Storey"],
    "Defence Colony": ["Defence Colony market", "Andrewsganj", "Kotla Mubarakpur", "Flyover market", "Sewa Nagar"],
    "Janakpuri": ["District Centre", "C-block market", "Janakpuri West metro", "Pankha Road", "Possangipur"],
    "Shahdara": ["Shahdara metro", "Jhilmil Colony", "Welcome", "GT Road", "Mansarovar Park"],
}

# crime_type: (relative frequency, peak hours, severity choices)
PROFILES = {
    "theft": (30, range(10, 21), (1, 2, 2, 3)),
    "vehicle_theft": (12, [22, 23, 0, 1, 2, 3, 4], (2, 3)),
    "chain_snatching": (8, [7, 8, 18, 19, 20], (3, 4)),
    "burglary": (8, [1, 2, 3, 4, 13, 14], (3, 4)),
    "assault": (10, [20, 21, 22, 23], (2, 3, 4)),
    "fraud": (12, range(10, 19), (2, 3)),
    "cybercrime": (6, range(9, 23), (2, 3)),
    "domestic_violence": (4, [21, 22, 23], (3, 4)),
    "robbery": (4, [21, 22, 23, 0], (4, 5)),
    "murder": (1, [22, 23, 0, 1], (5,)),
}

# Narratives are composed from independent fragments so unrelated incidents read differently, as real FIRs do.
# Only the planted series below shares a distinctive modus operandi.
NARRATIVE_PARTS = {
    "theft": (
        ["Mobile phone", "Wallet with cash and cards", "Laptop bag", "Purse", "Gas cylinder", "Copper wiring",
         "Bicycle", "Shop cash box", "Water pump", "Gold earrings"],
        ["taken from the complainant's bag in a crowded bus", "lifted from a shop counter", "removed from a parked car",
         "missing from the balcony", "stolen at the metro station platform", "taken from an unlocked godown",
         "picked from a trouser pocket at the weekly market", "stolen from a construction site"],
        ["No CCTV in the vicinity.", "A neighbour saw a youth in a grey hoodie.", "Complainant noticed the loss after an hour.",
         "Shopkeeper suspects a former helper.", "Footage from a nearby ATM camera requested.", "No suspect identified so far."],
    ),
    "vehicle_theft": (
        ["Splendor motorcycle", "Activa scooter", "Maruti Alto", "E-rickshaw", "Pulsar motorcycle", "Bolero pickup"],
        ["parked outside the residence went missing overnight", "stolen from the hospital parking",
         "taken from the office basement", "removed from the roadside near the dhaba", "stolen from the society gate"],
        ["Handle lock found broken.", "GPS tracker was disconnected.", "Duplicate key may have been used.",
         "Vehicle registration circulated to all stations.", "Owner discovered it at 6 am."],
    ),
    "chain_snatching": (
        ["A youth on foot", "Two persons on a red scooter", "A man posing as a delivery agent", "An unknown cyclist",
         "Two boys walking behind the victim"],
        ["snatched the mangalsutra of an elderly woman", "pulled the gold chain of a vegetable vendor",
         "snatched a chain near the temple gate", "grabbed the chain of a woman returning from the gym"],
        ["Accused fled into the lanes.", "Victim suffered minor neck abrasions.", "Passers-by gave a partial description.",
         "No vehicle number noted."],
    ),
    "burglary": (
        ["Lock of the main door was cut", "Rear window grill was removed", "Shutter of the shop was forced open",
         "Balcony door latch was broken", "Duplicate key appears to have been used"],
        ["while the family was at a wedding", "during the afternoon when the flat was empty", "on a Sunday night",
         "while the owners were out of station"],
        ["Cash and jewellery missing from the almirah.", "LED television and laptop taken.", "Locker found intact.",
         "Fingerprints lifted by the crime team.", "Watchman reported nothing unusual."],
    ),
    "assault": (
        ["Dispute over parking", "Argument at a liquor vend", "Quarrel between neighbours over water supply",
         "Road-rage incident after a minor collision", "Old enmity between two families"],
        ["led to the complainant being beaten with sticks", "ended with a punch that broke the victim's tooth",
         "escalated and the accused attacked with a rod", "resulted in a scuffle with three persons injured"],
        ["Victim referred to the government hospital.", "MLC obtained.", "Accused known to the complainant.",
         "Bystanders recorded a video of the incident."],
    ),
    "fraud": (
        ["Caller posing as a bank official", "Fake job portal", "Fraudulent property dealer", "Person claiming to be a relative abroad",
         "Fake electricity board message"],
        ["induced the complainant to share an OTP", "collected a registration fee and disappeared",
         "took an advance for a flat that did not exist", "asked for money for an emergency", "sent a link that installed a screen-sharing app"],
        ["Amount transferred through UPI.", "Money moved to a bank account in another state.", "Complainant approached the 1930 helpline.",
         "Transaction details obtained from the bank."],
    ),
    "cybercrime": (
        ["Social media account hacked", "Morphed photographs circulated", "Email account compromised",
         "Sextortion call received", "Fake profile created in the complainant's name"],
        ["and used to ask contacts for money", "on a messaging group", "and business contacts sent fake invoices",
         "with a demand for payment"],
        ["Platform requested to preserve logs.", "IP details sought from the service provider.", "Screenshots preserved as evidence."],
    ),
    "domestic_violence": (
        ["Complainant alleges cruelty by her husband", "Married woman reports harassment by in-laws",
         "Wife alleges physical abuse", "Complainant states she was thrown out of the matrimonial home"],
        ["over dowry demands", "after demanding her salary", "following repeated quarrels", "for not bearing a son"],
        ["Counselling at the women's cell attempted.", "Medical examination conducted.", "Statements of parents recorded."],
    ),
    "robbery": (
        ["Two armed men on a motorcycle", "Three persons in a car", "Two youths with a knife", "An armed gang of four"],
        ["robbed the complainant of cash near the ATM", "snatched a bag from a delivery agent", "looted a petrol pump attendant",
         "robbed a shopkeeper while closing"],
        ["Shots were not fired.", "Victim received a knife cut on the arm.", "CCTV footage partially captured the vehicle."],
    ),
    "murder": (
        ["Body of a male with stab wounds", "Woman found strangled", "Youth shot dead", "Body recovered from the canal"],
        ["near the railway line", "in a rented room", "behind a factory", "in a vacant plot"],
        ["Post-mortem conducted.", "Crime scene examined by forensic team.", "Family suspects a property dispute."],
    ),
}


def _narrative(crime_type: str) -> str:
    who, what, detail = NARRATIVE_PARTS[crime_type]
    return f"{RNG.choice(who)} {RNG.choice(what)}. {RNG.choice(detail)}"


SECTIONS = {
    "theft": ("379", "303(2)"), "vehicle_theft": ("379", "303(2)"), "chain_snatching": ("392", "309(4)"),
    "burglary": ("380", "305"), "assault": ("324", "118(1)"), "fraud": ("420", "318(4)"),
    "cybercrime": ("420", "318(4)"), "domestic_violence": ("498A", "85"), "robbery": ("392", "309(4)"),
    "murder": ("302", "103(1)"),
}
BNS_START = datetime(2024, 7, 1, tzinfo=UTC)
IST = timedelta(hours=5, minutes=30)

# Synthetic FIR openings in the languages Delhi stations actually receive, plus regional languages
# for the multilingual demo. Place names stay in Latin script, as they usually do in typed FIRs.
FIR_TEMPLATES = {
    "hi": "दिनांक {date} को {district} क्षेत्र में शिकायतकर्ता के साथ {crime} की घटना हुई। {detail} मामला धारा {section} {code} के तहत थाना {district} में दर्ज किया गया। संपर्क {phone}।",
    "hi-Latn": "{date} ko {district} mein shikayatkarta ke saath {crime} ki ghatna hui. {detail} Dhara {section} {code} ke tehat thana {district} mein FIR darj ki gayi.",
    "bn": "{date} তারিখে {district} এলাকায় অভিযোগকারীর সঙ্গে {crime} এর ঘটনা ঘটেছে। {detail} ধারা {section} {code} অনুযায়ী মামলা রুজু করা হয়েছে।",
    "mr": "{date} रोजी {district} परिसरात फिर्यादीसोबत {crime} ची घटना घडली. {detail} कलम {section} {code} प्रमाणे गुन्हा दाखल करण्यात आला.",
    "ta": "{date} அன்று {district} பகுதியில் புகார்தாரருக்கு எதிராக {crime} சம்பவம் நடந்தது. {detail} பிரிவு {section} {code} இன் கீழ் வழக்கு பதிவு செய்யப்பட்டது.",
    "te": "{date} న {district} ప్రాంతంలో ఫిర్యాదుదారుడిపై {crime} ఘటన జరిగింది. {detail} సెక్షన్ {section} {code} కింద కేసు నమోదు చేశారు.",
    "gu": "{date} ના રોજ {district} વિસ્તારમાં ફરિયાદી સાથે {crime} ની ઘટના બની. {detail} કલમ {section} {code} હેઠળ ગુનો નોંધાયો.",
    "kn": "{date} ರಂದು {district} ಪ್ರದೇಶದಲ್ಲಿ ದೂರುದಾರರ ಮೇಲೆ {crime} ಘಟನೆ ನಡೆದಿದೆ. {detail} ಕಲಂ {section} {code} ಅಡಿಯಲ್ಲಿ ಪ್ರಕರಣ ದಾಖಲಿಸಲಾಗಿದೆ.",
    "ml": "{date} ന് {district} പ്രദേശത്ത് പരാതിക്കാരനെതിരെ {crime} സംഭവം ഉണ്ടായി. {detail} വകുപ്പ് {section} {code} പ്രകാരം കേസ് രജിസ്റ്റർ ചെയ്തു.",
    "pa": "{date} ਨੂੰ {district} ਇਲਾਕੇ ਵਿੱਚ ਸ਼ਿਕਾਇਤਕਰਤਾ ਨਾਲ {crime} ਦੀ ਘਟਨਾ ਵਾਪਰੀ। {detail} ਧਾਰਾ {section} {code} ਤਹਿਤ ਮਾਮਲਾ ਦਰਜ ਕੀਤਾ ਗਿਆ।",
    "or": "{date} ରେ {district} ଅଞ୍ଚଳରେ ଅଭିଯୋଗକାରୀଙ୍କ ସହ {crime} ଘଟଣା ଘଟିଛି। {detail} ଧାରା {section} {code} ଅନୁଯାୟୀ ମାମଲା ରୁଜୁ ହୋଇଛି।",
    "ur": "{date} کو {district} کے علاقے میں شکایت کنندہ کے ساتھ {crime} کا واقعہ پیش آیا۔ {detail} دفعہ {section} {code} کے تحت مقدمہ درج کیا گیا۔",
    "as": "{date} তাৰিখে {district} অঞ্চলত অভিযোগকাৰীৰ সৈতে {crime}ৰ ঘটনা ঘটিছে। {detail} ধাৰা {section} {code} অনুসৰি গোচৰ পঞ্জীয়ন কৰা হৈছে।",
}
FIR_LANGUAGE_WEIGHTS = {
    "en": 32, "hi": 22, "hi-Latn": 8, "bn": 5, "mr": 5, "ta": 4, "te": 4, "gu": 4, "kn": 3, "ml": 3, "pa": 4,
    "or": 2, "ur": 3, "as": 2,
}
NATIVE_DIGITS = {
    "hi": "०१२३४५६७८९", "mr": "०१२३४५६७८९", "bn": "০১২৩৪৫৬৭৮৯", "as": "০১২৩৪৫৬৭৮৯",
}
CRIME_FALLBACK = {"chain_snatching": "robbery", "vehicle_theft": "theft", "burglary": "theft",
                  "cybercrime": "fraud", "domestic_violence": "assault"}


def _native(number: str, language: str) -> str:
    digits = NATIVE_DIGITS.get(language)
    return "".join(digits[int(ch)] if digits and ch.isdigit() else ch for ch in number)


_NOUN_OVERRIDES = {("hi", "chain_snatching"): "चेन स्नैचिंग", ("hi-Latn", "chain_snatching"): "chain snatching"}


def _crime_word(crime_type: str, language: str) -> str:
    if (language, crime_type) in _NOUN_OVERRIDES:
        return _NOUN_OVERRIDES[(language, crime_type)]
    terms = CRIME_TERMS.get(language, {})
    for wanted in (crime_type, CRIME_FALLBACK.get(crime_type), "theft"):
        word = next((term for term, concept in terms.items() if concept == wanted), None)
        if word:
            return word
    return crime_type.replace("_", " ")


def _fir_text(crime: "Crime", language: str, cited_section: str, code: str, detail: str = "") -> str:
    local = crime.occurred_at + IST  # FIRs are written in Indian Standard Time
    if language == "en":
        return (
            f"On {local:%d/%m/%Y} at about {local:%H:%M} hrs in {crime.district}: "
            f"{crime.description} {detail} Complainant contactable on 98{RNG.randint(10000000, 99999999)}. "
            f"Case registered u/s {cited_section} {code}."
        )
    return FIR_TEMPLATES[language].format(
        date=_native(f"{local:%d/%m/%Y}", language),
        district=crime.district,
        crime=_crime_word(crime.crime_type, language),
        detail=detail,
        section=_native(cited_section, language),
        code=code,
        phone=_native(f"98{RNG.randint(10000000, 99999999)}", language),
    )


def _jitter(lat: float, lng: float, km: float) -> tuple[float, float]:
    d = km / 111.0
    return lat + RNG.uniform(-d, d), lng + RNG.uniform(-d, d)


def _crime(crime_type: str, district: str, occurred: datetime, officer: User, **extra) -> Crime:
    _, _, severities = PROFILES[crime_type]
    lat, lng = _jitter(*DISTRICTS[district], km=2.0)
    lat, lng = extra.pop("coords", (lat, lng))
    ipc, bns = SECTIONS[crime_type]
    landmark = extra.pop("landmark", None) or RNG.choice(LANDMARKS[district])
    return Crime(
        crime_type=crime_type,
        location_name=landmark,
        address=f"Near {landmark}, {district}, New Delhi",
        description=extra.pop("description", None) or _narrative(crime_type),
        severity=extra.pop("severity", None) or RNG.choice(severities),
        district=district,
        city="Delhi",
        latitude=lat,
        longitude=lng,
        geom=func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
        occurred_at=occurred,
        status=extra.pop("status", RNG.choice(["reported", "under_investigation", "under_investigation", "resolved"])),
        case_number=f"DL-{occurred:%Y}-{secrets.token_hex(4).upper()}",
        assigned_officer_id=officer.id,
        legal_sections=extra.pop("legal_sections", None) or [bns if occurred >= BNS_START else ipc],
        **extra,
    )


def _occurrence(now: datetime, crime_type: str, span_days: int) -> datetime:
    _, hours, _ = PROFILES[crime_type]
    day = now - timedelta(days=RNG.randint(1, span_days))
    # Weekend nights see more street crime.
    if day.weekday() < 4 and crime_type in {"assault", "robbery"} and RNG.random() < 0.4:
        day += timedelta(days=4 - day.weekday())
    return day.replace(hour=RNG.choice(list(hours)), minute=RNG.randint(0, 59), second=0, microsecond=0) - IST


# Detailed scenarios layered over the background noise. Each one is a pattern a real
# district sees, built so the identifiers in the narratives link the cases together.
SYNDICATE = {
    # Cell 1: KYC-update callers. Cell 2: sextortion. Cell 3: fake instant-loan app.
    # One phone bridges cells 1 and 2, one mule account bridges cells 1 and 3.
    "kyc": [
        ("Connaught Place", 61_000, "SMS said the SBI YONO account would be blocked; caller from 9771203344 shared a link and the OTP was taken. Rs {amt} sent to kyc.update.sbi@ybl."),
        ("Karol Bagh", 24_500, "Retired teacher received a KYC call from 9771203344. Rs {amt} moved to A/c No. 50100234567812 (HDFC, Deoghar branch)."),
        ("Rohini", 99_999, "Fake KYC link; screen-sharing app installed. Rs {amt} withdrawn via kyc.update.sbi@ybl in three transfers."),
        ("Janakpuri", 15_000, "Caller from 7782041156 posing as bank staff asked to 'verify PAN'. Rs {amt} paid to kyc.update.sbi@ybl."),
        ("Shahdara", 42_300, "Pensioner got a KYC suspension call from 7782041156. Rs {amt} credited to account no 50100234567812."),
    ],
    "sextortion": [
        ("Saket", 30_000, "Video call from an unknown woman; recording used to threaten the complainant. Demand from 9771203344, Rs {amt} paid to rk.payments77@okicici."),
        ("Dwarka", 18_000, "Sextortion: caller from 8340127788 posing as a Delhi Police inspector demanded Rs {amt} to 'close the case' via rk.payments77@okicici."),
        ("Lajpat Nagar", 55_000, "Student threatened with morphed video; Rs {amt} paid in two parts to rk.payments77@okicici after calls from 8340127788."),
        ("Defence Colony", 12_000, "Businessman received an obscene video call then a demand from 8340127788 for Rs {amt}."),
    ],
    "loan": [
        ("Rohini", 8_500, "InstaCash loan app: Rs 5,000 loan, Rs {amt} 'processing fee' demanded with morphed photos sent to contacts. Repayment to instaloan.care@paytm."),
        ("Dwarka", 21_000, "Loan app recovery agent from 7004561290 abused the complainant; Rs {amt} paid to A/c 50100234567812."),
        ("Janakpuri", 13_750, "Fake loan app harassment; recovery calls from 7004561290, Rs {amt} paid to instaloan.care@paytm."),
        ("Saket", 46_000, "Complainant's contacts received morphed images after a loan app download. Rs {amt} paid to instaloan.care@paytm."),
        ("Karol Bagh", 9_900, "Loan app agent from 7004561290 threatened to post photos; Rs {amt} sent to instaloan.care@paytm."),
    ],
}

BURGLARY_GANG = [  # A white Swift Dzire seen near night-time break-ins in west Delhi.
    ("Janakpuri", 46, "C-block market", "Lock of a locked house cut while the family was in Haridwar; jewellery worth Rs 3.2 lakh taken. Neighbour saw a white Swift Dzire DL 8C AF 2210 at 2:40 am."),
    ("Janakpuri", 39, "Possangipur", "Rear window grill removed; cash and a laptop missing. Society camera shows a white Swift Dzire, number DL 8C AF 2210."),
    ("Dwarka", 31, "Sector 6 market", "Shop shutter forced open; Rs 1.1 lakh in cash taken. The night guard was called from 9899011223 to the gate just before; a Swift Dzire DL 8C AF 2210 was parked outside."),
    ("Dwarka", 22, "Sector 12 Venkateshwar complex", "Flat burgled while owners were abroad. Swift Dzire DL 8C AF 2210 seen leaving at 3 am."),
    ("Rohini", 15, "Sector 24 DDA flats", "Two flats on the same floor burgled; latch cut with a hydraulic cutter. Watchman received a call from 9899011223 asking about the owners."),
    ("Rohini", 6, "Sector 7 market", "Jewellery shop burglary foiled; accused fled in a white Swift Dzire DL 8C AF 2210."),
]

TWO_WHEELER_RING = [  # Bikes lifted in east and central Delhi, one of them later used in snatchings.
    ("vehicle_theft", "Shahdara", 58, "Welcome", "Splendor DL 5S BT 9087 stolen from outside the metro; handle lock broken."),
    ("vehicle_theft", "Shahdara", 51, "Jhilmil Colony", "Activa DL 5S CJ 1132 stolen from society parking at night."),
    ("vehicle_theft", "Karol Bagh", 44, "Tank Road", "Pulsar DL 2S AV 7781 stolen from the market parking; owner found the parking token cut."),
    ("chain_snatching", "Karol Bagh", 37, "Ajmal Khan Road", "Two youths on a Splendor DL 5S BT 9087 snatched a chain from a woman shopper."),
    ("robbery", "Connaught Place", 29, "Janpath market", "Mobile snatched at knifepoint by pillion rider of Splendor DL 5S BT 9087."),
    ("vehicle_theft", "Shahdara", 12, "GT Road", "Pulsar DL 2S AV 7781 recovered abandoned near the railway crossing; engine number tampered."),
]

EXTORTION = [  # Traders threatened over calls from one number.
    ("Karol Bagh", 26, "Ghaffar Market", "Mobile shop owner threatened by caller from 9654400771 claiming to be from a Haryana gang; demand of Rs 10 lakh."),
    ("Connaught Place", 21, "Inner Circle Block E", "Restaurant owner received WhatsApp voice notes from 9654400771 demanding Rs 25 lakh; shots fired at the shutter at night."),
    ("Karol Bagh", 14, "Pusa Road crossing", "Jeweller threatened over call from 9654400771; demand of Rs 50 lakh, family photographs sent."),
    ("Rohini", 7, "Adventure Island", "Property dealer received demand of Rs 5 lakh from 9654400771; caller named a jailed gangster."),
]

# Custody cases with remand and section data so both chargesheet tracks show up.
# (crime_type, sections, days since arrest, first remand offset in days or None, chargesheet filed)
CUSTODY = [
    ("murder", ["103(1)"], 86, 1, False),
    ("murder", ["103(1)", "3(5)"], 91, 1, False),
    ("robbery", ["309(4)"], 57, 1, False),
    ("robbery", ["310(2)"], 82, 2, False),
    ("burglary", ["305", "331(4)"], 58, 1, False),
    ("theft", ["303(2)"], 61, 1, False),
    ("fraud", ["318(4)", "319(2)"], 44, 1, False),
    ("assault", ["118(1)"], 35, None, False),
    ("domestic_violence", ["85", "115(2)"], 50, 1, False),
    ("chain_snatching", ["304"], 55, 1, False),
    ("murder", ["103(1)"], 70, 1, True),
    ("cybercrime", ["318(4)"], 20, 1, False),
]


def _operations(now: datetime, officers: list[User], station_officer: User) -> list[Crime]:
    ops: list[Crime] = []

    def at(days_ago: float, hours) -> datetime:
        return (now - timedelta(days=days_ago)).replace(hour=RNG.choice(list(hours)), minute=RNG.randint(0, 59),
                                                        second=0, microsecond=0) - IST

    day = 75
    for cell, rows in SYNDICATE.items():
        for district, amount, story in rows:
            day -= RNG.randint(2, 5)
            kind = "fraud" if cell == "kyc" else "cybercrime"
            ops.append(_crime(kind, district, at(max(day, 1), range(10, 20)), RNG.choice(officers),
                              description=story.format(amt=f"{amount:,}"), sub_type=cell))
    for district, days_ago, landmark, story in BURGLARY_GANG:
        ops.append(_crime("burglary", district, at(days_ago, [1, 2, 3]), RNG.choice(officers),
                          description=story, landmark=landmark, sub_type="house_break_in"))
    for crime_type, district, days_ago, landmark, story in TWO_WHEELER_RING:
        ops.append(_crime(crime_type, district, at(days_ago, range(19, 24)), RNG.choice(officers),
                          description=story, landmark=landmark))
    for district, days_ago, landmark, story in EXTORTION:
        ops.append(_crime("robbery", district, at(days_ago, range(11, 22)), RNG.choice(officers),
                          description=story, landmark=landmark, sub_type="extortion", severity=5))
    for crime_type, sections, days, remand, filed in CUSTODY:
        arrested = now - timedelta(days=days, hours=RNG.randint(0, 8))
        ops.append(_crime(
            crime_type, RNG.choice(list(DISTRICTS)), arrested - timedelta(days=RNG.randint(1, 4)), station_officer,
            status="under_investigation",
            accused_arrested_at=arrested,
            accused_first_remanded_at=arrested + timedelta(days=remand) if remand is not None else None,
            chargesheet_filed_at=arrested + timedelta(days=days - 3) if filed else None,
            legal_sections=sections,
        ))
    return ops


async def seed(db: AsyncSession, n_crimes: int, force: bool) -> None:
    existing = (await db.execute(text("SELECT COUNT(*) FROM users"))).scalar_one()
    if existing and not force:
        print(f"Database already has {existing} users; pass --force to seed anyway.")
        return

    password = os.environ.get("SEED_PASSWORD") or secrets.token_urlsafe(12) + "aA1"
    users = {
        role: User(email=f"{role}@crimeai.example", hashed_password=hash_password(password),
                   full_name=f"Demo {role.title()}", role=role, badge_number=f"DL-{i:04d}")
        for i, role in enumerate(("admin", "analyst", "police", "readonly"), start=1)
    }
    officers = [users["police"]] + [
        User(email=f"officer{i:02d}@crimeai.example", hashed_password=hash_password(password),
             full_name=f"Officer {i:02d}", role="police", badge_number=f"DL-{100 + i}")
        for i in range(1, 6)
    ]
    db.add_all([*users.values(), *officers[1:]])
    await db.flush()

    now = datetime.now(UTC)
    weights = [p[0] for p in PROFILES.values()]
    district_weights = [5, 3, 4, 3, 2, 3, 2, 2, 4]
    crimes = []
    for _ in range(n_crimes):
        crime_type = RNG.choices(list(PROFILES), weights)[0]
        district = RNG.choices(list(DISTRICTS), district_weights)[0]
        crimes.append(_crime(crime_type, district, _occurrence(now, crime_type, 540), RNG.choice(officers)))

    planted: list[Crime] = []
    # A serial chain-snatching team working the Lajpat Nagar / Defence Colony border every ~3 days.
    spree_mo = ("Two men on a black Pulsar without number plate; pillion rider in a red helmet snatched the "
                "gold chain of a woman walking near the market and fled towards the ring road.")
    spree_mo_hi = ("काली पल्सर मोटरसाइकिल पर बिना नंबर प्लेट के दो लड़के आए। पीछे बैठे लाल हेलमेट वाले ने बाज़ार के पास "
                   "पैदल जा रही महिला की सोने की चेन छीनी और रिंग रोड की ओर भाग गए।")
    spree_plate = " A witness later noted the motorcycle as DL 3S CK 4471."
    for k in range(6):
        district = ("Lajpat Nagar", "Defence Colony")[k % 2]
        occurred = (now - timedelta(days=20 - 3 * k)).replace(hour=19, minute=RNG.randint(0, 50)) - IST
        description = spree_mo_hi if k in (1, 4) else spree_mo + (spree_plate if k in (2, 5) else "")
        planted.append(_crime("chain_snatching", district, occurred, officers[1], description=description,
                             coords=_jitter(28.5700, 77.2370, km=0.8)))

    # Cyber-fraud mule ring: one UPI handle and one phone recur across complaints in four districts.
    mule_upi, mule_phone = "refund.helpdesk@okaxis", "9810012345"
    fraud_ring = [
        ("Connaught Place", f"Caller posing as a courier agent asked for a Rs 4,999 redelivery fee to {mule_upi}."),
        ("Rohini", f"Fake electricity disconnection message; victim called {mule_phone} and paid Rs 12,000 to {mule_upi}."),
        ("Saket", f"OLX buyer sent a QR code; Rs 38,500 debited to {mule_upi}."),
        ("Shahdara", f"Caller from {mule_phone} claimed to be a bank official and took the OTP; Rs 61,000 lost."),
        ("Dwarka", f"Job offer fee of Rs 2,500 paid to {mule_upi}; follow-up calls from {mule_phone}."),
        ("Karol Bagh", f"Sextortion call from {mule_phone} demanding money."),
    ]
    for i, (district, story) in enumerate(fraud_ring):
        occurred = (now - timedelta(days=40 - 6 * i)).replace(hour=RNG.randint(10, 19), minute=RNG.randint(0, 59)) - IST
        planted.append(_crime("fraud" if i != 5 else "cybercrime", district, occurred, RNG.choice(officers),
                             description=story))

    # Stolen-bike ring: a motorcycle reported stolen in Rohini is used in robberies elsewhere days later.
    bike = "HR 26 DQ 5551"
    bike_cases = [
        ("vehicle_theft", "Rohini", 33, f"Black Apache motorcycle {bike} stolen from outside a gym; handle lock broken."),
        ("robbery", "Janakpuri", 27, f"Two men on a motorcycle bearing {bike} robbed a delivery agent at knifepoint."),
        ("chain_snatching", "Dwarka", 24, f"Pillion rider on motorcycle {bike} snatched a chain near the metro station."),
        ("robbery", "Dwarka", 19, f"Petrol pump attendant robbed by two men; CCTV shows motorcycle {bike}."),
    ]
    for crime_type, district, days_ago, story in bike_cases:
        occurred = (now - timedelta(days=days_ago)).replace(hour=RNG.randint(20, 23), minute=RNG.randint(0, 59)) - IST
        planted.append(_crime(crime_type, district, occurred, RNG.choice(officers), description=story))

    planted += _operations(now, officers, users["police"])
    crimes += planted

    db.add_all(crimes)
    await db.flush()

    firs = []
    # Every planted scenario gets an FIR, so its identifiers also reach the graph through the FIR reader.
    languages, weights_by_language = zip(*FIR_LANGUAGE_WEIGHTS.items(), strict=True)
    for crime in planted + RNG.sample(crimes[:n_crimes], 104):
        ipc, bns = SECTIONS.get(crime.crime_type, ("379", "303(2)"))
        modern = crime.occurred_at >= BNS_START
        language = "en" if crime in planted and RNG.random() < 0.5 else RNG.choices(languages, weights_by_language)[0]
        detail = crime.description if crime in planted and language != "en" else ""
        firs.append(FIRReport(
            fir_number=f"FIR/{crime.district[:3].upper()}/{crime.occurred_at:%Y}/{secrets.token_hex(3).upper()}",
            crime_id=crime.id,
            submitted_by=crime.assigned_officer_id,
            incident_date=crime.occurred_at,
            raw_text=_fir_text(crime, language, bns if modern else ipc, "BNS" if modern else "IPC", detail),
            nlp_status="pending",
        ))
    recent = next(c for c in crimes if c.occurred_at > BNS_START + timedelta(days=30))
    firs.append(FIRReport(
        fir_number="FIR/DEMO/WRONG-CODE",
        crime_id=recent.id,
        submitted_by=recent.assigned_officer_id,
        incident_date=recent.occurred_at,
        raw_text=f"{recent.description} Case registered u/s 379, 411 IPC although the incident is after 1 July 2024.",
        nlp_status="pending",
    ))
    db.add_all(firs)
    await db.commit()

    print(f"Seeded {len(users) + len(officers) - 1} users, {len(crimes)} crimes, {len(firs)} FIRs.")
    print("Users: admin@ / analyst@ / police@ / readonly@crimeai.example and officer01-05@crimeai.example")
    if not os.environ.get("SEED_PASSWORD"):
        print(f"Generated password for all seed users (shown once): {password}")
    print("Next: run the worker, then POST /api/v1/ml/hotspot-prediction and /api/v1/intel/series/detect.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--crimes", type=int, default=3000)
    args = parser.parse_args()
    if settings.is_production:
        sys.exit("Refusing to seed a production database.")
    engine = create_async_engine(settings.DATABASE_URL)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        await seed(db, args.crimes, args.force)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
