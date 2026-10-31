"""Multilingual FIR understanding across scripts and languages."""
import pytest

from app.nlp.legal.bns_crosswalk import analyse_sections
from app.nlp.multilingual import analyse, detect_language, normalise_digits, normalise_for_legal
from app.nlp.parsers.fir_pipeline import process_fir_text

SAMPLES = {
    "hi": ("शिकायतकर्ता की मोटरसाइकिल DL 3S CK 4471 चोरी हो गई और आरोपी के पास चाकू था। धारा ३७९ भा.दं.सं.", "theft"),
    "mr": ("फिर्यादी यांच्या घरात घरफोडी झाली आहे आणि दागिने चोरीला गेले. कलम ३८०", "burglary"),
    "bn": ("অভিযোগকারীর মোবাইল ফোন চুরি হয়েছে। অভিযুক্তের হাতে ছুরি ছিল। ধারা ৩৭৯", "theft"),
    "ta": ("புகார்தாரரின் தங்க சங்கிலி வழிப்பறி செய்யப்பட்டது. குற்றவாளி கத்தி வைத்திருந்தார்.", "chain_snatching"),
    "te": ("ఫిర్యాదుదారుడి ఇంట్లో దొంగతనం జరిగింది. నిందితుడి వద్ద కత్తి ఉంది.", "theft"),
    "gu": ("ફરિયાદીના ઘરમાં ચોરી થઈ હતી.", "theft"),
    "kn": ("ದೂರುದಾರರ ಮನೆಯಲ್ಲಿ ಕಳ್ಳತನ ನಡೆದಿದೆ.", "theft"),
    "ml": ("പരാതിക്കാരന്റെ വീട്ടിൽ മോഷണം നടന്നു.", "theft"),
    "pa": ("ਸ਼ਿਕਾਇਤਕਰਤਾ ਦੀ ਗੱਡੀ ਚੋਰੀ ਹੋ ਗਈ। ਦੋਸ਼ੀ ਕੋਲ ਪਿਸਤੌਲ ਸੀ।", "theft"),
    "or": ("ଅଭିଯୋଗକାରୀଙ୍କ ଘରେ ଚୋରି ହୋଇଛି।", "theft"),
    "ur": ("شکایت کنندہ کا موبائل چوری ہو گیا اور ملزم کے پاس چاقو تھا۔", "theft"),
    "as": ("অভিযোগকাৰীৰ ঘৰত চুৰি হৈছে।", "theft"),
    "hi-Latn": ("Shikayatkarta ka mobile chori ho gaya aur ek ke paas chaku tha. Thana Saket mein FIR darj ki gayi.", "theft"),
    "en": ("Two men on a motorcycle snatched the gold chain of the complainant near the market.", "chain_snatching"),
}


@pytest.mark.parametrize(("expected_language", "sample"), list(SAMPLES.items()))
def test_language_and_crime_detected(expected_language, sample):
    text, crime = sample
    result = analyse(text)
    assert result.language == expected_language
    assert result.crime_type == crime


def test_indic_digits_normalised_without_shifting_offsets():
    text = "धारा ३७९ और ৪২০"
    assert normalise_digits(text) == "धारा 379 और 420"
    assert len(normalise_digits(text)) == len(text)


@pytest.mark.parametrize(
    ("text", "section"),
    [("मामला धारा ३७९ भा.दं.सं. के तहत दर्ज", "379"), ("ধারা ৩৭৯ অনুযায়ী", "379"), ("دفعہ 379 کے تحت", "379"),
     ("कलम ३८० भा.दं.वि.", "380")],
)
def test_sections_read_in_native_words_and_digits(text, section):
    assert section in [c["section"] for c in analyse_sections(normalise_for_legal(text))["citations"]]


def test_hindi_code_word_resolves_to_ipc():
    citations = analyse_sections(normalise_for_legal("धारा ३७९ भा.दं.सं."))["citations"]
    assert citations[0]["code"] == "IPC"


def test_identifiers_extracted_from_indic_text():
    result = analyse("आरोपी DL 3S CK 4471 पर था, संपर्क ९८७६५४३२१०, भुगतान refund.desk@okaxis पर रु. 25,000")
    assert result.vehicles == ["DL3SCK4471"]
    assert result.phones == ["9876543210"]
    assert result.upi_ids == ["refund.desk@okaxis"]
    assert 25000.0 in result.amounts


def test_highlights_point_at_the_original_text():
    text = SAMPLES["hi"][0]
    for h in analyse(text).highlights:
        assert text[h.start:h.end] == h.text


def test_shared_script_disambiguation():
    assert detect_language("तो घरी आहे आणि त्यांनी फिर्याद दिली")[0] == "mr"
    assert detect_language("उहाँ घरमा हुनुहुन्छ र प्रहरीलाई खबर गरेको थियो")[0] == "ne"
    assert detect_language("Two men stole the phone")[0] == "en"


def test_pipeline_runs_without_spacy_for_indic_fir():
    out = process_fir_text(SAMPLES["bn"][0] + " অভিযোগকারীর ফোন ৯৮৭৬৫৪৩২১০।")
    entities = out["entities"]
    assert entities["language"]["code"] == "bn"
    assert entities["crime_type"] == "theft"
    assert "knife" in entities["weapons"]
    assert entities["privacy"]["pii_found"] == {"PHONE": 1}
    assert entities["identifiers"]["phones"][0].endswith("210")


TELUGU_COMPLAINT = (
    "విషయం: - పందిరి రిణశేఖర్ GPA డాక్యుమెంట్లు మీద సంతకాలు మరియు థంబ్ ఇంప్రెస్సిఒన్ వేరు వేరుగా ఉన్నాయి. "
    "సూచన:- ఈ తేదీ 8-12-2016న GPA చేసినవారు పేరు 1. పందిరి రిణశేఖర్. నేను ప్రైవేట్ కంప్లైంటు బోనగిరి కోర్టుల్లో "
    "ఫైలు చేసిన తేదీ 23-2-2012 ఆ తర్వాత FIR No. 212/2012 తేదీ 18-8-2012 నమోదయ్యింది"
)


def test_telugu_forgery_complaint_is_understood():
    """A real-style Telugu petition about forged GPA signatures: language, offence, FIR reference and dates."""
    result = analyse(TELUGU_COMPLAINT)
    assert result.language == "te"
    assert result.crime_type == "fraud"
    assert result.fir_references == ["212/2012"]
    assert result.dates == ["2012-02-23", "2012-08-18", "2016-12-08"]
    glosses = {h.gloss for h in result.highlights}
    assert "signatures (document evidence)" in glosses and "general power of attorney" in glosses


def test_signature_alone_is_weak_evidence():
    scores = analyse("Complainant signature verified at the station.").crime_scores
    assert scores.get("fraud", 0) <= 1.0


def test_terms_match_through_zero_width_joiners():
    """Indic OCR output carries ZWNJ characters inside words ("థంబ్‌ ఇంప్రెస్"); matching must survive them."""
    text = "సంతకాలు మరియు థంబ్\u200c ఇంప్రెస్\u200cసిఒన్ వేరుగా ఉన్నాయి"
    highlights = analyse(text).highlights
    thumb = [h for h in highlights if h.gloss.startswith("thumb")]
    assert thumb and text[thumb[0].start:thumb[0].end] == thumb[0].text


def test_superscripts_and_fractions_on_scanned_forms_are_left_alone():
    # OCR of FIR forms yields "2½ km" and "m²": digits to Python's isdigit, but not decimal digits.
    assert normalise_digits("২½ km, ৩² m, १२") == "2½ km, 3² m, 12"
