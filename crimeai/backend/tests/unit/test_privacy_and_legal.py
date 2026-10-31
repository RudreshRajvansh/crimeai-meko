"""PII redaction and IPC/BNS section analysis."""
from datetime import date

import pytest

from app.nlp.legal.bns_crosswalk import analyse_sections, extract_citations, governing_code
from app.nlp.privacy.redaction import redact, verhoeff_valid


def _valid_aadhaar(prefix: str = "49871234567") -> str:
    return next(prefix + d for d in "0123456789" if verhoeff_valid(prefix + d))


class TestRedaction:
    def test_redacts_common_identifiers(self):
        aadhaar = _valid_aadhaar()
        text = (
            f"Aadhaar {aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}, mobile +91 98765 43210, "
            "mail a.b@gmail.com, PAN ABCPK1234F, a/c no 123456789012, UPI ravi@okaxis"
        )
        result = redact(text)
        for secret in (aadhaar[:4], "98765", "a.b@gmail.com", "ABCPK1234F", "123456789012", "ravi@okaxis"):
            assert secret not in result.text
        assert set(result.counts) == {"AADHAAR", "PHONE", "EMAIL", "PAN", "BANK_ACCOUNT", "UPI"}

    def test_twelve_digit_number_failing_checksum_is_kept(self):
        invalid = next(
            n for n in (f"4987123456{a}{b}" for a in "0123456789" for b in "0123456789") if not verhoeff_valid(n)
        )
        assert invalid in redact(f"Case ref {invalid}").text

    def test_clean_text_untouched(self):
        result = redact("Two men on a motorcycle snatched a chain near the market at 7 pm.")
        assert not result.redacted

    def test_verhoeff_known_values(self):
        assert verhoeff_valid("2363") and not verhoeff_valid("2364")


class TestLegalSections:
    def test_governing_code_switches_on_commencement(self):
        assert governing_code(date(2024, 6, 30)) == "IPC"
        assert governing_code(date(2024, 7, 1)) == "BNS"

    def test_extracts_grouped_citations_with_code(self):
        citations = extract_citations("registered u/s 379, 411 IPC and section 34 of the Indian Penal Code")
        assert {(c.section, c.code) for c in citations} == {("379", "IPC"), ("411", "IPC"), ("34", "IPC")}

    def test_ipc_after_commencement_is_flagged_and_mapped(self):
        result = analyse_sections("u/s 420 IPC", date(2025, 1, 10))
        assert result["mapped"][0]["bns"] == "318(4)"
        assert result["suggested_crime_type"] == "fraud"
        assert result["warnings"]

    def test_bns_before_commencement_is_flagged(self):
        result = analyse_sections("u/s 303(2) BNS", date(2024, 1, 10))
        assert result["mapped"][0]["ipc"] == "379"
        assert any("before 1 July 2024" in w for w in result["warnings"])

    def test_repealed_section_has_explanation(self):
        mapped = analyse_sections("u/s 377 IPC", date(2023, 1, 1))["mapped"][0]
        assert mapped["bns"] is None and mapped["note"]

    @pytest.mark.parametrize("text", ["", "no sections here", "section"])
    def test_no_citations(self, text):
        assert analyse_sections(text)["citations"] == []
