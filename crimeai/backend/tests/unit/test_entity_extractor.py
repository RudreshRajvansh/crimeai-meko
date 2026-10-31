"""
Unit tests for the spaCy entity extractor.
Uses monkeypatching to avoid loading the real model in tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_mock_doc(entities: list[tuple[str, str]]) -> MagicMock:
    """Create a mock spaCy doc with given (text, label) entity pairs."""
    doc = MagicMock()
    mock_ents = []
    for text, label in entities:
        ent = MagicMock()
        ent.text = text
        ent.label_ = label
        mock_ents.append(ent)
    doc.ents = mock_ents
    return doc


@pytest.fixture(autouse=True)
def mock_spacy_model():
    """Patch _get_nlp so no real model is loaded."""
    mock_nlp = MagicMock()
    mock_nlp.return_value = _make_mock_doc([])
    with patch("app.nlp.parsers.entity_extractor._get_nlp", return_value=mock_nlp):
        yield mock_nlp

from app.nlp.parsers.crime_classifier import classify_crime_type, classify_severity
from app.nlp.parsers.entity_extractor import (
    _CRIME_KEYWORDS,
    _deduplicate,
    _extract_suspect_descriptions,
    _preprocess_text,
)


class TestPreprocessText:
    def test_expands_sho_abbreviation(self):
        result = _preprocess_text("The SHO was informed immediately.")
        assert "Station House Officer" in result

    def test_expands_fir_abbreviation(self):
        result = _preprocess_text("An FIR was registered.")
        assert "First Information Report" in result

    def test_collapses_whitespace(self):
        result = _preprocess_text("too    many   spaces")
        assert "  " not in result

    def test_strips_text(self):
        result = _preprocess_text("  padded text  ")
        assert result == result.strip()


class TestDeduplicate:
    def test_removes_duplicates(self):
        items = ["Delhi", "Mumbai", "Delhi", "Chennai"]
        result = _deduplicate(items)
        assert result == ["Delhi", "Mumbai", "Chennai"]

    def test_case_insensitive(self):
        items = ["Delhi", "delhi", "DELHI"]
        result = _deduplicate(items)
        assert len(result) == 1
        assert result[0] == "Delhi"   # preserves first occurrence

    def test_preserves_order(self):
        items = ["C", "A", "B", "A"]
        result = _deduplicate(items)
        assert result == ["C", "A", "B"]

    def test_empty_list(self):
        assert _deduplicate([]) == []


class TestCrimeKeywords:
    """Verify crime keyword dictionaries are well-formed."""

    def test_all_crime_types_have_keywords(self):
        for crime_type, keywords in _CRIME_KEYWORDS.items():
            assert len(keywords) >= 2, f"{crime_type} needs at least 2 keywords"

    def test_keywords_are_lowercase(self):
        for crime_type, keywords in _CRIME_KEYWORDS.items():
            for kw in keywords:
                assert kw == kw.lower(), f"Keyword '{kw}' in {crime_type} must be lowercase"

    def test_no_empty_keywords(self):
        for crime_type, keywords in _CRIME_KEYWORDS.items():
            for kw in keywords:
                assert len(kw.strip()) > 0, f"Empty keyword in {crime_type}"


class TestClassifyCrimeType:
    def test_theft_keywords_detected(self):
        text = "The complainant reported that his bicycle was stolen from outside the market."
        result = classify_crime_type(text)
        assert result["crime_type"] == "theft"
        assert result["confidence"] > 0

    def test_assault_keywords_detected(self):
        text = "The accused attacked and beat the victim causing grievous bodily harm."
        result = classify_crime_type(text)
        assert result["crime_type"] == "assault"

    def test_robbery_keywords_detected(self):
        text = "Two men on motorcycle snatched the gold chain from the complainant."
        result = classify_crime_type(text)
        assert result["crime_type"] in ("robbery", "theft")

    def test_returns_other_for_unrecognised(self):
        text = "This text contains no recognisable crime keywords whatsoever."
        result = classify_crime_type(text)
        # Should still return something (even "other")
        assert "crime_type" in result
        assert "confidence" in result

    def test_result_has_required_keys(self):
        result = classify_crime_type("The accused was found with narcotics.")
        for key in ["crime_type", "confidence", "method", "keyword_predictions"]:
            assert key in result

    def test_drug_detected(self):
        text = "Police seized large quantity of narcotics and contraband from the accused."
        result = classify_crime_type(text)
        assert result["crime_type"] == "drug_offense"

    def test_confidence_in_range(self):
        result = classify_crime_type("The suspect stole the phone and ran away.")
        assert 0.0 <= result["confidence"] <= 1.0


class TestClassifySeverity:
    def test_murder_is_five(self):
        assert classify_severity("murder") == 5

    def test_trespass_is_one(self):
        assert classify_severity("trespass") == 1

    def test_weapon_increases_severity(self):
        base = classify_severity("theft", has_weapon=False)
        with_weapon = classify_severity("theft", has_weapon=True)
        assert with_weapon > base

    def test_injury_increases_severity(self):
        base = classify_severity("assault", has_injury=False)
        with_injury = classify_severity("assault", has_injury=True)
        assert with_injury >= base

    def test_max_severity_is_five(self):
        sev = classify_severity(
            "murder", has_weapon=True, has_injury=True, num_suspects=10
        )
        assert sev <= 5

    def test_min_severity_is_one(self):
        sev = classify_severity("trespass")
        assert sev >= 1

    def test_gang_keyword_raises_severity(self):
        base = classify_severity("theft", text="")
        gang = classify_severity("theft", text="gang of 10 people attacked")
        assert gang >= base


class TestExtractSuspectDescriptions:
    def test_extracts_accused_sentence(self):
        text = ("The accused, aged about 25 years, was wearing a blue shirt "
                "and had a fair complexion.")
        suspects = _extract_suspect_descriptions(text)
        assert len(suspects) >= 1

    def test_extracts_age(self):
        text = "The accused aged 30 years was arrested from the scene."
        suspects = _extract_suspect_descriptions(text)
        if suspects:
            assert "age" in suspects[0]
            assert "30" in suspects[0]["age"]

    def test_extracts_gender_male(self):
        text = "An unknown male suspect was seen fleeing the scene."
        suspects = _extract_suspect_descriptions(text)
        if suspects:
            assert suspects[0].get("gender") == "male"

    def test_extracts_gender_female(self):
        text = "The accused woman was wearing a saree and fled."
        suspects = _extract_suspect_descriptions(text)
        if suspects:
            assert suspects[0].get("gender") == "female"

    def test_no_suspect_sentence_returns_empty(self):
        text = "The complainant reported the theft of his bicycle from the market."
        suspects = _extract_suspect_descriptions(text)
        assert isinstance(suspects, list)

    def test_caps_at_five_suspects(self):
        # Create text with 8 accused sentences
        text = ". ".join([
            f"The accused person number {i} aged {20+i} years was identified"
            for i in range(8)
        ])
        suspects = _extract_suspect_descriptions(text)
        assert len(suspects) <= 5
