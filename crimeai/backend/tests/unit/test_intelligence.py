"""Crime series linkage and the custody clock."""
import random
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.ml.linkage.series_detector import Incident, detect_series
from app.services.custody_clock import compute_deadline, escalation_for, limit_days_for, track_for

BASE = datetime(2025, 5, 1, 19, tzinfo=UTC)
MO = "Two men on a black motorcycle without number plate snatched a gold chain, pillion rider wore a helmet"


def _spree(n=5, district_cycle=("Lajpat Nagar", "Defence Colony")):
    rng = random.Random(7)
    return [
        Incident(
            id=f"s{i}", crime_type="chain_snatching",
            lat=28.56 + rng.uniform(-0.008, 0.008), lng=77.24 + rng.uniform(-0.008, 0.008),
            occurred_at=BASE + timedelta(days=3 * i), text=MO, district=district_cycle[i % len(district_cycle)],
        )
        for i in range(n)
    ]


def _noise(n=40):
    rng = random.Random(11)
    texts = ["mobile stolen from bag in crowded bus", "purse snatched by a boy on foot", "laptop stolen from car"]
    return [
        Incident(
            id=f"n{i}", crime_type="chain_snatching",
            lat=28.4 + rng.random() * 0.4, lng=76.9 + rng.random() * 0.5,
            occurred_at=BASE + timedelta(days=rng.randint(0, 60)), text=rng.choice(texts),
        )
        for i in range(n)
    ]


class TestSeriesDetection:
    def test_finds_cross_jurisdiction_spree(self):
        found = detect_series(_spree() + _noise(), min_similarity=0.5)
        assert len(found) == 1
        series = found[0].to_dict()
        assert set(series["incident_ids"]) == {f"s{i}" for i in range(5)}
        assert series["cross_jurisdiction"] is True
        assert series["next_window"] is not None

    def test_series_id_is_stable_as_series_grows(self):
        first = detect_series(_spree(4), min_similarity=0.5)[0].series_id
        grown = detect_series(_spree(6), min_similarity=0.5)[0].series_id
        assert first == grown

    def test_incidents_far_apart_in_time_are_not_linked(self):
        spaced = _spree()
        for i, incident in enumerate(spaced):
            incident.occurred_at = BASE + timedelta(days=60 * i)
        assert detect_series(spaced, window_days=21, min_similarity=0.5) == []

    def test_different_crime_types_never_link(self):
        mixed = _spree()
        for incident in mixed[::2]:
            incident.crime_type = "theft"
        assert all(len(s.incident_ids) >= 3 and s.crime_type for s in detect_series(mixed, min_similarity=0.5))
        assert not any({"s0", "s1"} <= set(s.incident_ids) for s in detect_series(mixed, min_similarity=0.5))

    def test_uses_embeddings_when_present(self):
        spree = _spree()
        for incident in spree:
            incident.embedding = np.ones(8)
        assert detect_series(spree, min_similarity=0.99)[0].cohesion == pytest.approx(1.0)


class TestCustodyClock:
    @staticmethod
    def _case(crime_type="theft", days_in_custody=50, sections=None):
        return SimpleNamespace(
            id="c1", case_number="CRM-1", crime_type=crime_type, district="Saket", assigned_officer_id=None,
            legal_sections=sections, accused_arrested_at=datetime.now(UTC) - timedelta(days=days_in_custody),
        )

    def test_limits(self):
        assert limit_days_for("murder", ["103(1)"]) == 90
        assert limit_days_for("theft", None) == 60
        assert limit_days_for("robbery", ["310(2)"]) == 90

    def test_track_follows_the_section_not_the_crime_type(self):
        """Stalking (BNS 78) and wrongful confinement (127(2)) carry well under ten years: 60-day cases."""
        assert limit_days_for("sexual_offense", ["78"]) == 60
        assert limit_days_for("kidnapping", ["127(2)"]) == 60

    def test_pre_bns_cases_map_ipc_sections(self):
        before_bns = datetime(2024, 3, 1, tzinfo=UTC)
        assert limit_days_for("murder", ["302"], before_bns) == 90
        assert limit_days_for("sexual_offense", ["354D"], before_bns) == 60

    def test_uncertain_track_takes_the_earlier_deadline_and_says_so(self):
        no_section = track_for("murder", None)
        assert no_section.limit_days == 60 and no_section.needs_verification
        attempt = track_for("assault", ["109"])
        assert attempt.limit_days == 60 and attempt.needs_verification
        assert not track_for("murder", ["103"]).needs_verification

    def test_escalation_bands(self):
        assert escalation_for(30) is None
        assert escalation_for(15) == "medium"
        assert escalation_for(7) == "high"
        assert escalation_for(1) == "critical"
        assert escalation_for(-3) == "critical"

    def test_theft_case_at_day_50_is_due_soon(self):
        deadline = compute_deadline(self._case())
        # Day of arrest is day one, so after 50 days in custody day 60 is 9 calendar days away.
        assert deadline.limit_days == 60 and deadline.days_remaining == 9 and deadline.status == "due_soon"
        assert deadline.clock_starts == "arrest" and deadline.approximate

    def test_clock_runs_from_first_remand_when_recorded(self):
        case = self._case(days_in_custody=50)
        case.accused_first_remanded_at = case.accused_arrested_at + timedelta(days=2)
        deadline = compute_deadline(case)
        assert deadline.days_remaining == 11 and deadline.clock_starts == "remand" and not deadline.approximate

    @pytest.mark.parametrize("now_ist", ["23:59", "00:01", "05:29"])
    def test_dates_are_counted_in_ist_not_utc(self, now_ist):
        """Between 00:00 and 05:30 IST the UTC date lags a day; the count must not shift with it."""
        ist = ZoneInfo("Asia/Kolkata")
        arrest = datetime(2026, 1, 1, 1, 0, tzinfo=ist)  # 31 Dec in UTC
        case = self._case()
        case.accused_arrested_at = arrest
        hour, minute = map(int, now_ist.split(":"))
        day = 30 if now_ist == "23:59" else 31
        now = datetime(2026, 1, day, hour, minute, tzinfo=ist)
        expected = (date(2026, 3, 1) - now.date()).days  # 60th day, counting 1 Jan as day one
        assert compute_deadline(case, now).days_remaining == expected
        assert compute_deadline(case, now).deadline.date() == date(2026, 3, 1)

    def test_overdue(self):
        assert compute_deadline(self._case(days_in_custody=65)).status == "overdue"


class TestSeriesPrecision:
    def test_ordinary_same_type_incidents_do_not_chain_into_a_series(self):
        """Regression: with a fixed threshold, routine thefts sharing generic wording chained into giant 'series'."""
        rng = random.Random(5)
        parts = (
            ["Mobile phone", "Wallet", "Laptop bag", "Purse", "Bicycle", "Cash box"],
            ["taken from a bag in a bus", "lifted from a shop counter", "removed from a parked car", "stolen at the metro"],
            ["No CCTV nearby.", "No suspect identified.", "Complainant noticed later.", "Footage requested."],
        )
        routine = [
            Incident(
                id=f"r{i}", crime_type="theft", lat=28.60 + rng.uniform(-0.01, 0.01), lng=77.20 + rng.uniform(-0.01, 0.01),
                occurred_at=BASE + timedelta(days=rng.randint(0, 20)),
                text=" ".join(rng.choice(p) for p in parts),
            )
            for i in range(80)
        ]
        planted = [
            Incident(
                id=f"p{i}", crime_type="theft", lat=28.60, lng=77.20, occurred_at=BASE + timedelta(days=2 * i),
                text="Thief cut the bottom of the complainant's sling bag with a blade inside the Route 534 bus near Sarai Kale Khan",
            )
            for i in range(4)
        ]
        found = detect_series(routine + planted, min_similarity=0.5)
        assert any(set(s.incident_ids) == {f"p{i}" for i in range(4)} for s in found)
        assert all(len(s.incident_ids) <= 6 for s in found)

    def test_pruning_removes_a_bridging_incident(self):
        from app.ml.linkage.series_detector import _prune

        sim = np.array([
            [1.0, 0.9, 0.9, 0.5],
            [0.9, 1.0, 0.9, 0.5],
            [0.9, 0.9, 1.0, 0.8],
            [0.5, 0.5, 0.8, 1.0],
        ])
        assert _prune([0, 1, 2, 3], sim, bar=np.full_like(sim, 0.8), min_size=3) == [0, 1, 2]


def test_embedding_text_excludes_place_names():
    """Regression: 'in <district>' in the embedded text split one cross-station series into two."""
    from app.ml.similarity.crime_similarity import crime_document

    a = crime_document("chain_snatching", None, "Two men on a black Pulsar snatched a chain", "Lajpat Nagar")
    b = crime_document("chain_snatching", None, "Two men on a black Pulsar snatched a chain", "Defence Colony")
    assert a == b and "Lajpat" not in a


def test_language_gap_calibration_links_cross_language_reports():
    """Same MO in Hindi and English scores lower in multilingual embeddings; calibration restores the link."""
    from app.ml.linkage.series_detector import calibrate_for_language, language_gap

    rng = np.random.default_rng(0)
    n_en, n_hi = 30, 30
    langs = ["en"] * n_en + ["hi"] * n_hi
    sim = np.full((60, 60), 0.86)
    same = np.asarray(langs)[:, None] == np.asarray(langs)[None, :]
    sim[same] = 0.90
    sim += rng.normal(0, 0.005, sim.shape)
    sim = (sim + sim.T) / 2
    np.fill_diagonal(sim, 1.0)
    assert language_gap(sim, langs) == pytest.approx(0.04, abs=0.01)
    calibrated, _ = calibrate_for_language(sim, langs)
    assert abs(np.median(calibrated[:n_en, n_en:]) - np.median(calibrated[:n_en, :n_en][np.triu_indices(n_en, 1)])) < 0.01


def test_no_calibration_without_enough_pairs():
    from app.ml.linkage.series_detector import language_gap

    assert language_gap(np.eye(4), ["en", "en", "hi", "hi"]) == 0.0


def test_a_large_series_does_not_shut_out_its_members_reported_in_another_language():
    """
    Regression: the similarity bar was the 99th percentile of every pair, so a series of near-identical English
    reports, together with look-alike unrelated reports, pushed it above the Hindi members' cross-language
    similarity. Cross-language pairs are now judged against other cross-language pairs that cannot share a series.
    """
    from app.ml.linkage.series_detector import _prune, adaptive_threshold

    rng = np.random.default_rng(1)
    n_series, n_noise = 6, 60
    n = n_series + n_noise
    langs = np.array(["en", "hi", "en", "en", "hi", "en"] + ["en"] * (n_noise - 10) + ["hi"] * 10)
    cross = langs[:, None] != langs[None, :]
    sim = np.where(cross, 0.88, 0.95) + rng.normal(0, 0.01, (n, n))  # unrelated reports already read alike
    sim[:n_series, :n_series] = np.where(cross[:n_series, :n_series], 0.949, 0.99)
    sim = np.clip((sim + sim.T) / 2, 0, 1)
    np.fill_diagonal(sim, 1.0)
    candidates = np.zeros((n, n), dtype=bool)
    candidates[:n_series, :n_series] = True  # only the series is close in place and time

    same_bar = adaptive_threshold(sim, 0.72, 0.99, background=~candidates)
    cross_bar = adaptive_threshold(sim, 0.72, 0.99, background=~candidates & cross, fallback=same_bar)
    assert cross_bar < 0.949 < same_bar, "one bar for both scales would drop the Hindi reports"

    bar = np.where(cross, cross_bar, same_bar)
    assert _prune(list(range(n_series)), sim, bar, min_size=3) == list(range(n_series))
