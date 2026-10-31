"""
Multilingual policing lexicons.

Seed vocabulary for crime types, weapons and legal terms in the languages
FIRs are most often written in, plus romanised Hindi (Hinglish). Each term
maps to a canonical English concept so highlights can carry a gloss and
classification works the same way in every language.

This is a seed, not a dictionary: field FIRs will surface regional and
dialect terms that should be added here (and reviewed by native speakers)
before an operational deployment. Semantic understanding of everything the
lexicon misses comes from the multilingual embedding model.
"""
from __future__ import annotations

# 22 languages of the Eighth Schedule plus English, with the script(s) each is usually written in.
LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English", "script": "Latin"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "script": "Devanagari"},
    "bn": {"name": "Bengali", "native": "বাংলা", "script": "Bengali"},
    "te": {"name": "Telugu", "native": "తెలుగు", "script": "Telugu"},
    "mr": {"name": "Marathi", "native": "मराठी", "script": "Devanagari"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "script": "Tamil"},
    "ur": {"name": "Urdu", "native": "اردو", "script": "Arabic"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "script": "Gujarati"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "script": "Kannada"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "script": "Malayalam"},
    "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "script": "Odia"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "script": "Gurmukhi"},
    "as": {"name": "Assamese", "native": "অসমীয়া", "script": "Bengali"},
    "mai": {"name": "Maithili", "native": "मैथिली", "script": "Devanagari"},
    "sat": {"name": "Santali", "native": "ᱥᱟᱱᱛᱟᱲᱤ", "script": "Ol Chiki"},
    "ks": {"name": "Kashmiri", "native": "کٲشُر", "script": "Arabic"},
    "ne": {"name": "Nepali", "native": "नेपाली", "script": "Devanagari"},
    "kok": {"name": "Konkani", "native": "कोंकणी", "script": "Devanagari"},
    "sd": {"name": "Sindhi", "native": "سنڌي", "script": "Arabic"},
    "doi": {"name": "Dogri", "native": "डोगरी", "script": "Devanagari"},
    "mni": {"name": "Manipuri", "native": "ꯃꯤꯇꯩꯂꯣꯟ", "script": "Meetei Mayek"},
    "brx": {"name": "Bodo", "native": "बड़ो", "script": "Devanagari"},
    "sa": {"name": "Sanskrit", "native": "संस्कृतम्", "script": "Devanagari"},
    "hi-Latn": {"name": "Hinglish", "native": "Hinglish", "script": "Latin"},
}

# Words that distinguish languages sharing a script. Scored by occurrence; the highest wins.
MARKERS: dict[str, list[str]] = {
    "hi": ["है", "हैं", "और", "की", "के", "में", "था", "थी", "गया", "किया", "ने", "से", "को", "तहत", "हुई",
           "दिनांक", "शिकायतकर्ता"],
    "mr": ["आहे", "आणि", "झाली", "झाला", "केली", "केले", "त्यांनी", "मध्ये", "होते", "फिर्याद", "यांनी", "रोजी",
           "घडली", "गुन्हा", "दाखल", "करण्यात", "आला", "ची", "प्रमाणे", "फिर्यादी", "परिसरात"],
    "ne": ["छ", "छन्", "थियो", "भएको", "गरेको", "गरे", "हो", "लाई", "बाट"],
    "kok": ["आसा", "जाल्लें", "हांव", "आनी", "जाल्लो", "करून"],
    "mai": ["अछि", "छथि", "भेल", "हम", "छल", "सँ"],
    "doi": ["ऐ", "दा", "दी", "गेआ", "होई", "ते"],
    "brx": ["आरो", "जायो", "दङ", "नि", "बाव"],
    "sa": ["अस्ति", "इति", "तस्य", "सः", "च", "भवति"],
    "ur": ["ہے", "کے", "میں", "اور", "کی", "تھا", "گیا", "نے"],
    "ks": ["چھُ", "چھ", "تہٕ", "کٔر", "اوس"],
    "sd": ["آهي", "جي", "۾", "ڪيو", "هو", "ٿيو"],
    "hi-Latn": ["hai", "hain", "nahi", "kiya", "gaya", "tha", "aur", "ke", "ki", "mein", "ko", "se", "thana",
                "shikayat", "chori", "maarpeet", "marpeet", "loot", "bhai", "unhone", "diya"],
}

# term -> canonical crime_type
CRIME_TERMS: dict[str, dict[str, str]] = {
    "hi": {
        "चोरी": "theft", "चुरा": "theft", "चोर": "theft", "लूटपाट": "robbery", "लूट": "robbery",
        "डकैती": "robbery", "छीन": "chain_snatching", "झपट": "chain_snatching", "चेन स्नैचिंग": "chain_snatching",
        "हत्या": "murder", "कत्ल": "murder", "क़त्ल": "murder", "मारपीट": "assault", "हमला": "assault",
        "पिटाई": "assault", "अपहरण": "kidnapping", "अगवा": "kidnapping", "धोखाधड़ी": "fraud", "ठगी": "fraud",
        "जालसाजी": "fraud", "बलात्कार": "sexual_offense", "छेड़छाड़": "sexual_offense", "दहेज": "domestic_violence",
        "घरेलू हिंसा": "domestic_violence", "सेंधमारी": "burglary", "वाहन चोरी": "vehicle_theft",
        "गाड़ी चोरी": "vehicle_theft", "मोटरसाइकिल चोरी": "vehicle_theft",
    },
    "mr": {
        "चोरी": "theft", "चोरीला": "theft", "घरफोडी": "burglary", "दरोडा": "robbery", "जबरी चोरी": "robbery",
        "खून": "murder", "मारहाण": "assault", "अपहरण": "kidnapping", "फसवणूक": "fraud",
        "बलात्कार": "sexual_offense", "विनयभंग": "sexual_offense", "हुंडा": "domestic_violence",
    },
    "bn": {
        "চুরি": "theft", "ছিনতাই": "chain_snatching", "ডাকাতি": "robbery", "খুন": "murder", "হত্যা": "murder",
        "মারধর": "assault", "অপহরণ": "kidnapping", "প্রতারণা": "fraud", "ধর্ষণ": "sexual_offense",
        "শ্লীলতাহানি": "sexual_offense", "পণ": "domestic_violence",
    },
    "as": {
        "চুৰি": "theft", "ডকাইতি": "robbery", "হত্যা": "murder", "মাৰপিট": "assault", "অপহৰণ": "kidnapping",
        "প্ৰতাৰণা": "fraud",
    },
    "ta": {
        "திருட்டு": "theft", "திருடப்பட்ட": "theft", "கொள்ளை": "robbery", "வழிப்பறி": "chain_snatching",
        "கொலை": "murder", "தாக்குதல்": "assault", "கடத்தல்": "kidnapping", "மோசடி": "fraud",
        "பாலியல் வன்கொடுமை": "sexual_offense", "வரதட்சணை": "domestic_violence",
    },
    "te": {
        "దొంగతనం": "theft", "దోపిడీ": "robbery", "హత్య": "murder", "దాడి": "assault", "కిడ్నాప్": "kidnapping",
        "అపహరణ": "kidnapping", "మోసం": "fraud", "అత్యాచారం": "sexual_offense", "వరకట్నం": "domestic_violence",
    },
    "gu": {
        "ચોરી": "theft", "લૂંટ": "robbery", "હત્યા": "murder", "ખૂન": "murder", "મારામારી": "assault",
        "હુમલો": "assault", "અપહરણ": "kidnapping", "છેતરપિંડી": "fraud", "બળાત્કાર": "sexual_offense",
        "દહેજ": "domestic_violence",
    },
    "kn": {
        "ಕಳ್ಳತನ": "theft", "ದರೋಡೆ": "robbery", "ಕೊಲೆ": "murder", "ಹಲ್ಲೆ": "assault", "ಅಪಹರಣ": "kidnapping",
        "ವಂಚನೆ": "fraud", "ಅತ್ಯಾಚಾರ": "sexual_offense", "ವರದಕ್ಷಿಣೆ": "domestic_violence",
    },
    "ml": {
        "മോഷണം": "theft", "കവർച്ച": "robbery", "കൊലപാതകം": "murder", "ആക്രമണം": "assault",
        "തട്ടിക്കൊണ്ടുപോ": "kidnapping", "തട്ടിപ്പ്": "fraud", "ബലാത്സംഗം": "sexual_offense",
        "സ്ത്രീധനം": "domestic_violence",
    },
    "pa": {
        "ਚੋਰੀ": "theft", "ਲੁੱਟ": "robbery", "ਕਤਲ": "murder", "ਹੱਤਿਆ": "murder", "ਕੁੱਟਮਾਰ": "assault",
        "ਅਗਵਾ": "kidnapping", "ਧੋਖਾਧੜੀ": "fraud", "ਬਲਾਤਕਾਰ": "sexual_offense", "ਦਾਜ": "domestic_violence",
    },
    "or": {
        "ଚୋରି": "theft", "ଡକାୟତି": "robbery", "ଲୁଟ": "robbery", "ହତ୍ୟା": "murder", "ମାଡ଼": "assault",
        "ଆକ୍ରମଣ": "assault", "ଅପହରଣ": "kidnapping", "ଠକେଇ": "fraud", "ଦୁଷ୍କର୍ମ": "sexual_offense",
        "ଯୌତୁକ": "domestic_violence",
    },
    "ur": {
        "چوری": "theft", "ڈکیتی": "robbery", "لوٹ": "robbery", "قتل": "murder", "مار پیٹ": "assault",
        "حملہ": "assault", "اغوا": "kidnapping", "دھوکہ دہی": "fraud", "زیادتی": "sexual_offense",
        "جہیز": "domestic_violence",
    },
    "hi-Latn": {
        "chori": "theft", "chor": "theft", "lootpaat": "robbery", "loot": "robbery", "dakaiti": "robbery",
        "chheen": "chain_snatching", "chain kheench": "chain_snatching", "hatya": "murder", "qatl": "murder",
        "katl": "murder", "maarpeet": "assault", "marpeet": "assault", "pitai": "assault", "hamla": "assault",
        "apharan": "kidnapping", "agwa": "kidnapping", "dhokhadhadi": "fraud", "thagi": "fraud",
        "balatkar": "sexual_offense", "chhedchhad": "sexual_offense", "dahej": "domestic_violence",
    },
}

WEAPON_TERMS: dict[str, dict[str, str]] = {
    "hi": {"चाकू": "knife", "छुरा": "knife", "पिस्तौल": "pistol", "तमंचा": "country-made pistol",
           "कट्टा": "country-made pistol", "बंदूक": "gun", "लाठी": "stick", "डंडा": "stick", "रॉड": "rod"},
    "mr": {"चाकू": "knife", "कोयता": "sickle", "पिस्तूल": "pistol", "काठी": "stick"},
    "bn": {"ছুরি": "knife", "পিস্তল": "pistol", "লাঠি": "stick", "বন্দুক": "gun"},
    "ta": {"கத்தி": "knife", "துப்பாக்கி": "gun", "அரிவாள்": "sickle"},
    "te": {"కత్తి": "knife", "తుపాకీ": "gun"},
    "gu": {"છરી": "knife", "તલવાર": "sword", "પિસ્તોલ": "pistol"},
    "kn": {"ಚಾಕು": "knife", "ಪಿಸ್ತೂಲ್": "pistol"},
    "ml": {"കത്തി": "knife", "തോക്ക്": "gun"},
    "pa": {"ਚਾਕੂ": "knife", "ਪਿਸਤੌਲ": "pistol"},
    "or": {"ଛୁରୀ": "knife"},
    "ur": {"چاقو": "knife", "پستول": "pistol", "بندوق": "gun"},
    "hi-Latn": {"chaku": "knife", "chhura": "knife", "katta": "country-made pistol", "tamancha": "country-made pistol",
                "lathi": "stick", "danda": "stick"},
}

# Native words for "section" and the two penal codes, normalised so one parser handles every language.
SECTION_WORDS = ["धारा", "कलम", "ধারা", "ধাৰা", "பிரிவு", "సెక్షన్", "కలం", "કલમ", "ಕಲಂ", "ಸೆಕ್ಷನ್", "വകുപ്പ്",
                 "ਧਾਰਾ", "ଧାରା", "دفعہ", "dhara"]
CODE_WORDS: dict[str, str] = {
    "भारतीय दंड संहिता": "IPC", "भा.दं.सं.": "IPC", "भा.दं.सं": "IPC", "आईपीसी": "IPC", "भा.दं.वि.": "IPC",
    "भारतीय दंड विधान": "IPC", "ভারতীয় দণ্ডবিধি": "IPC", "இந்திய தண்டனைச் சட்டம்": "IPC", "تعزیرات ہند": "IPC",
    "भारतीय न्याय संहिता": "BNS", "बीएनएस": "BNS", "ভারতীয় ন্যায় সংহিতা": "BNS", "भा.न्या.सं.": "BNS",
}
POLICE_STATION_WORDS = ["थाना", "पोलीस ठाणे", "থানা", "காவல் நிலையம்", "పోలీస్ స్టేషన్", "પોલીસ સ્ટેશન",
                        "ಪೊಲೀಸ್ ಠಾಣೆ", "പോലീസ് സ്റ്റേഷൻ", "ਥਾਣਾ", "ଥାନା", "تھانہ", "thana", "police station"]

ENGLISH_CRIME_TERMS: dict[str, str] = {
    "stolen": "theft", "theft": "theft", "stole": "theft", "pickpocket": "theft", "snatched": "chain_snatching",
    "chain snatching": "chain_snatching", "robbed": "robbery", "robbery": "robbery", "dacoity": "robbery",
    "looted": "robbery", "murder": "murder", "killed": "murder", "stab wounds": "murder", "assault": "assault",
    "beaten": "assault", "attacked": "assault", "kidnapped": "kidnapping", "abducted": "kidnapping",
    "cheated": "fraud", "fraud": "fraud", "otp": "fraud", "rape": "sexual_offense", "molested": "sexual_offense",
    "dowry": "domestic_violence", "cruelty": "domestic_violence", "burgled": "burglary", "house break": "burglary",
    "lock broken": "burglary", "motorcycle stolen": "vehicle_theft", "vehicle theft": "vehicle_theft",
}
ENGLISH_WEAPON_TERMS: dict[str, str] = {
    "knife": "knife", "knifepoint": "knife", "pistol": "pistol", "country-made pistol": "country-made pistol",
    "gun": "gun", "revolver": "gun", "rod": "rod", "iron rod": "rod", "stick": "stick", "lathi": "stick",
    "sword": "sword", "sickle": "sickle", "acid": "acid",
}

CRIME_LABELS: dict[str, str] = {
    "theft": "theft", "robbery": "robbery", "chain_snatching": "chain snatching", "murder": "murder",
    "assault": "assault", "kidnapping": "kidnapping", "fraud": "fraud / cheating", "sexual_offense": "sexual offence",
    "domestic_violence": "domestic violence / dowry", "burglary": "burglary", "vehicle_theft": "vehicle theft",
}

# Document fraud (forgery, fake signatures and thumb impressions, power-of-attorney fraud) is one of the most
# common complaint types in land and property disputes. Terms map to the "fraud" offence category (BNS 336-340,
# formerly IPC 467/468/471) but keep their own gloss so officers see exactly what was recognised.
FORGERY_TERMS: dict[str, dict[str, str]] = {
    "te": {"ఫోర్జరీ": "forgery", "నకిలీ": "fake / counterfeit", "సంతకాలు": "signatures (document evidence)",
           "సంతకం": "signature (document evidence)", "థంబ్ ఇంప్రెస్": "thumb impression (document evidence)",
           "వేలిముద్ర": "thumb / finger impression", "జీపీఏ": "general power of attorney"},
    "hi": {"फर्जी": "fake / forged", "कूटरचना": "forgery", "हस्ताक्षर": "signature (document evidence)",
           "अंगूठे का निशान": "thumb impression (document evidence)", "मुख्तारनामा": "power of attorney"},
    "mr": {"बनावट": "fake / forged", "खोटी सही": "forged signature", "सही": "signature (document evidence)",
           "अंगठ्याचा ठसा": "thumb impression (document evidence)", "कुलमुखत्यारपत्र": "power of attorney"},
    "bn": {"জাল": "fake / forged", "জালিয়াতি": "forgery", "স্বাক্ষর": "signature (document evidence)",
           "টিপসই": "thumb impression (document evidence)"},
    "ta": {"போலி": "fake / forged", "கையொப்பம்": "signature (document evidence)",
           "கைரேகை": "thumb / finger impression"},
    "kn": {"ನಕಲಿ": "fake / forged", "ಸಹಿ": "signature (document evidence)",
           "ಹೆಬ್ಬೆರಳಿನ ಗುರುತು": "thumb impression (document evidence)"},
    "ml": {"വ്യാജ": "fake / forged", "ഒപ്പ്": "signature (document evidence)",
           "വിരലടയാളം": "thumb / finger impression"},
    "gu": {"બનાવટી": "fake / forged", "સહી": "signature (document evidence)",
           "અંગૂઠાનું નિશાન": "thumb impression (document evidence)"},
    "pa": {"ਜਾਅਲੀ": "fake / forged", "ਦਸਤਖ਼ਤ": "signature (document evidence)"},
    "or": {"ଜାଲ": "fake / forged", "ଦସ୍ତଖତ": "signature (document evidence)"},
    "ur": {"جعلی": "fake / forged", "جعلسازی": "forgery", "دستخط": "signature (document evidence)",
           "انگوٹھے کا نشان": "thumb impression (document evidence)"},
    "hi-Latn": {"farzi": "fake / forged", "jaali": "fake / forged", "hastakshar": "signature (document evidence)"},
    "en": {"forged": "forgery", "forgery": "forgery", "fake document": "fake document", "fabricated": "forgery",
           "signature": "signature (document evidence)", "signatures": "signatures (document evidence)",
           "thumb impression": "thumb impression (document evidence)", "power of attorney": "power of attorney",
           "gpa": "general power of attorney", "sale deed": "property document"},
}

TERM_GLOSSES: dict[str, str] = {}
for _lang, _terms in FORGERY_TERMS.items():
    target = ENGLISH_CRIME_TERMS if _lang == "en" else CRIME_TERMS.setdefault(_lang, {})
    for _term, _gloss in _terms.items():
        target.setdefault(_term, "fraud")
        TERM_GLOSSES[_term.lower()] = _gloss

# Generic words that support but never decide a classification on their own.
WEAK_EVIDENCE_TERMS = {t.lower() for terms in FORGERY_TERMS.values() for t, g in terms.items() if "evidence" in g or "attorney" in g}
