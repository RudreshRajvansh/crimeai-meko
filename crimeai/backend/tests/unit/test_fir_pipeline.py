"""
Unit tests for the FIR processing pipeline.
spaCy model is mocked so these run without the actual model.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_mock_doc(entities=None):
    doc = MagicMock()
    if entities is None:
        entities = []
    mock_ents = []
    for text, label in entities:
        ent = MagicMock()
        ent.text = text
        ent.label_ = label
        mock_ents.append(ent)
    doc.ents = mock_ents
    return doc


@pytest.fixture(autouse=True)
def mock_spacy():
    mock_nlp = MagicMock()
    mock_nlp.return_value = _make_mock_doc([
        ("Connaught Place", "GPE"),
        ("14:30", "TIME"),
    ])
    with patch("app.nlp.parsers.entity_extractor._get_nlp", return_value=mock_nlp):
        yield


from app.nlp.parsers.fir_pipeline import PIPELINE_VERSION, _mentions_injury
from app.nlp.parsers.fir_pipeline import process_fir_text as _process


def process_fir_text(text, **kwargs):
    return _process(text, **kwargs)["entities"]


SAMPLE_FIR = """
On 15/06/2024 at approximately 14:30 hours, the complainant Rajesh Kumar
reported to Police Station Connaught Place that his motorcycle bearing
registration number DL-01-AB-1234 was stolen from the parking area near
Palika Bazaar. The accused, aged about 25 years with fair complexion,
was wearing a blue shirt and jeans. The accused was seen fleeing with
a knife in his hand. IPC Section 379 and 411 have been invoked.
"""


class TestProcessFirText:
    def test_returns_dict(self):
        result = process_fir_text(SAMPLE_FIR)
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        result = process_fir_text(SAMPLE_FIR)
        required = [
            "locations", "crime_type", "weapons", "suspects",
            "time_references", "overall_confidence",
            "processed_at", "pipeline_version",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_detects_theft_crime_type(self):
        result = process_fir_text(SAMPLE_FIR)
        assert result["crime_type"] == "theft"

    def test_detects_knife_weapon(self):
        result = process_fir_text(SAMPLE_FIR)
        assert "knife" in result["weapons"]

    def test_has_weapon_flag(self):
        result = process_fir_text(SAMPLE_FIR)
        assert result["has_weapon"] is True

    def test_legal_sections_mapped_to_bns(self):
        result = process_fir_text(SAMPLE_FIR)
        mapped = {m["ipc"]: m["bns"] for m in result["legal"]["mapped"]}
        assert mapped.get("379") == "303(2)"

    def test_redacted_copy_returned(self):
        output = _process(SAMPLE_FIR + " Contact 9876543210.")
        assert "9876543210" not in output["redacted_text"]
        assert output["entities"]["privacy"]["pii_found"] == {"PHONE": 1}

    def test_confidence_in_valid_range(self):
        result = process_fir_text(SAMPLE_FIR)
        assert 0.0 <= result["overall_confidence"] <= 1.0

    def test_inferred_severity_in_range(self):
        result = process_fir_text(SAMPLE_FIR)
        assert 1 <= result["inferred_severity"] <= 5

    def test_fir_number_stored(self):
        result = process_fir_text(SAMPLE_FIR, fir_number="FIR-2024-001")
        assert result["fir_number"] == "FIR-2024-001"

    def test_pipeline_version_present(self):
        result = process_fir_text(SAMPLE_FIR)
        assert result["pipeline_version"] == PIPELINE_VERSION

    def test_very_short_text_raises(self):
        from app.core.exceptions import NLPServiceError
        with pytest.raises(NLPServiceError, match="too short"):
            process_fir_text("too short")

    def test_empty_text_raises(self):
        from app.core.exceptions import NLPServiceError
        with pytest.raises(NLPServiceError):
            process_fir_text("")

    def test_assault_fir(self):
        text = (
            "The accused attacked and beat the complainant with an iron rod "
            "near Lajpat Nagar market at 22:00 hours causing grievous injuries. "
            "The victim was hospitalised. IPC Section 323 and 324 applied."
        )
        result = process_fir_text(text)
        assert result["crime_type"] == "assault"
        assert result["has_injury"] is True

    def test_drug_offense_fir(self):
        text = (
            "Police personnel arrested the accused at Rohini sector 7. "
            "Large quantity of narcotics including heroin was seized. "
            "IPC and NDPS Act sections invoked."
        )
        result = process_fir_text(text)
        assert result["crime_type"] == "drug_offense"


class TestTextMentionsInjury:
    def test_injured_detected(self):
        assert _mentions_injury("The victim was injured in the attack.") is True

    def test_hospitalised_detected(self):
        assert _mentions_injury("He was hospitalised for treatment.") is True

    def test_no_injury(self):
        assert _mentions_injury("The vehicle was stolen from the parking lot.") is False

    def test_dead_detected(self):
        assert _mentions_injury("The body of the deceased was found.") is True
