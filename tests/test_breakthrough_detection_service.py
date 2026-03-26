"""Unit tests for BreakthroughDetectionService (Layer D Step 5.1).

Covers:
  - _poisson_neg_log_prob: normal, edge, negative-k crash guard
  - _viterbi_states: burst detection, flat series, single year
  - _kleinberg_burst_score: normal, no citations, one year
  - _centrality_shift_score: growing, declining, flat, < 2 years
  - detect(): happy path, parameter validation, negative-count guard, empty input
"""

import math
import pytest

from aievograph.domain.ports.citation_time_series_repository import (
    CitationTimeSeriesRepositoryPort,
)
from aievograph.domain.services.breakthrough_detection_service import (
    BreakthroughDetectionService,
    _centrality_shift_score,
    _kleinberg_burst_score,
    _poisson_neg_log_prob,
    _viterbi_states,
)


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------

class StubTimeSeriesRepo(CitationTimeSeriesRepositoryPort):
    """Returns a pre-set time series regardless of arguments."""

    def __init__(self, data: dict[str, dict[int, int]]) -> None:
        self._data = data

    def get_yearly_citation_counts(
        self,
        paper_ids: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[int, int]]:
        return self._data


# ---------------------------------------------------------------------------
# _poisson_neg_log_prob
# ---------------------------------------------------------------------------

class TestPoissonNegLogProb:
    def test_lam_zero_k_zero_returns_zero(self):
        assert _poisson_neg_log_prob(0, 0.0) == 0.0

    def test_lam_zero_k_positive_returns_large(self):
        assert _poisson_neg_log_prob(3, 0.0) == 1e18

    def test_lam_negative_treated_as_zero(self):
        # lam <= 0 branch; k=0 → 0.0
        assert _poisson_neg_log_prob(0, -1.0) == 0.0

    def test_normal_poisson_k0_lam1(self):
        # -ln P(0|Poisson(1)) = 1 - 0*ln(1) + lgamma(1) = 1 + 0 = 1.0
        result = _poisson_neg_log_prob(0, 1.0)
        assert math.isclose(result, 1.0, rel_tol=1e-9)

    def test_normal_poisson_k1_lam1(self):
        # -ln P(1|Poisson(1)) = 1 - 1*ln(1) + lgamma(2) = 1 - 0 + 0 = 1.0
        result = _poisson_neg_log_prob(1, 1.0)
        assert math.isclose(result, 1.0, rel_tol=1e-9)

    def test_large_k_no_crash(self):
        # lgamma(101) must not raise; result must be finite
        result = _poisson_neg_log_prob(100, 50.0)
        assert math.isfinite(result)

    def test_negative_k_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            _poisson_neg_log_prob(-1, 1.0)

    def test_negative_k_large_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            _poisson_neg_log_prob(-9, 5.0)

    def test_zero_k_any_positive_lam(self):
        result = _poisson_neg_log_prob(0, 5.0)
        # = 5.0 - 0 + lgamma(1) = 5.0
        assert math.isclose(result, 5.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# _viterbi_states
# ---------------------------------------------------------------------------

class TestViterbiStates:
    def test_empty_counts_returns_empty(self):
        assert _viterbi_states([], q0=1.0, s=2.0, gamma=1.0) == []

    def test_single_year_no_citations(self):
        states = _viterbi_states([0], q0=0.0, s=2.0, gamma=1.0)
        assert len(states) == 1

    def test_flat_low_counts_stay_background(self):
        # Very low counts — should prefer state 0
        states = _viterbi_states([1, 1, 1, 1, 1], q0=1.0, s=2.0, gamma=1.0)
        assert len(states) == 5
        # At least some years in state 0
        assert 0 in states

    def test_burst_in_later_years(self):
        # Low counts early, high counts late → late years likely burst
        counts = [0, 0, 0, 10, 20, 30]
        states = _viterbi_states(counts, q0=sum(counts) / len(counts), s=2.0, gamma=1.0)
        assert len(states) == 6
        # Later years should be in burst state more than early
        early_burst = sum(states[:3])
        late_burst = sum(states[3:])
        assert late_burst >= early_burst

    def test_all_zeros_no_crash(self):
        states = _viterbi_states([0, 0, 0], q0=0.0, s=2.0, gamma=1.0)
        assert len(states) == 3
        assert all(s in (0, 1) for s in states)

    def test_output_states_are_binary(self):
        counts = [3, 5, 2, 8, 1]
        states = _viterbi_states(counts, q0=4.0, s=2.0, gamma=1.0)
        assert all(s in (0, 1) for s in states)

    def test_returns_correct_length(self):
        counts = list(range(10))
        states = _viterbi_states(counts, q0=5.0, s=2.0, gamma=1.0)
        assert len(states) == 10


# ---------------------------------------------------------------------------
# _kleinberg_burst_score
# ---------------------------------------------------------------------------

class TestKleinbergBurstScore:
    def test_no_citations_returns_zero(self):
        score = _kleinberg_burst_score({}, 2010, 2020, s=2.0, gamma=1.0)
        assert score == 0.0

    def test_single_year_window_returns_zero_or_nonzero(self):
        # T=1, all weight in one year; result is either 0.0 or 1.0
        score = _kleinberg_burst_score({2020: 5}, 2020, 2020, s=2.0, gamma=1.0)
        assert 0.0 <= score <= 1.0

    def test_result_in_unit_interval(self):
        counts = {2015: 1, 2016: 1, 2017: 10, 2018: 20, 2019: 15}
        score = _kleinberg_burst_score(counts, 2015, 2019, s=2.0, gamma=1.0)
        assert 0.0 <= score <= 1.0

    def test_burst_in_recent_years_scores_higher_than_flat(self):
        # Strong recent burst
        burst_counts = {2018: 0, 2019: 0, 2020: 50}
        flat_counts = {2018: 5, 2019: 5, 2020: 5}
        burst_score = _kleinberg_burst_score(burst_counts, 2018, 2020, s=2.0, gamma=1.0)
        flat_score = _kleinberg_burst_score(flat_counts, 2018, 2020, s=2.0, gamma=1.0)
        # Burst concentrated in the last year (highest recency weight) should win
        assert burst_score >= flat_score

    def test_missing_years_treated_as_zero(self):
        # Only year 2020 has citations; 2018 and 2019 default to 0
        score = _kleinberg_burst_score({2020: 10}, 2018, 2020, s=2.0, gamma=1.0)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _centrality_shift_score
# ---------------------------------------------------------------------------

class TestCentralityShiftScore:
    def test_single_year_returns_zero(self):
        assert _centrality_shift_score({2020: 10}, 2020, 2020) == 0.0

    def test_growing_paper_positive_shift(self):
        # Past: 1,1  Recent: 10,10 → positive shift
        counts = {2010: 1, 2011: 1, 2012: 10, 2013: 10}
        shift = _centrality_shift_score(counts, 2010, 2013)
        assert shift > 0

    def test_declining_paper_negative_shift(self):
        counts = {2010: 10, 2011: 10, 2012: 1, 2013: 1}
        shift = _centrality_shift_score(counts, 2010, 2013)
        assert shift < 0

    def test_flat_paper_zero_shift(self):
        counts = {2010: 5, 2011: 5, 2012: 5, 2013: 5}
        shift = _centrality_shift_score(counts, 2010, 2013)
        assert math.isclose(shift, 0.0, abs_tol=1e-9)

    def test_no_citations_returns_zero(self):
        shift = _centrality_shift_score({}, 2010, 2015)
        assert shift == 0.0

    def test_two_year_window(self):
        # T=2: mid=1, past=[2010], recent=[2011]
        counts = {2010: 2, 2011: 8}
        shift = _centrality_shift_score(counts, 2010, 2011)
        assert math.isclose(shift, 6.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# BreakthroughDetectionService.detect()
# ---------------------------------------------------------------------------

class TestDetect:
    def _make_service(self, data: dict[str, dict[int, int]]) -> BreakthroughDetectionService:
        return BreakthroughDetectionService(StubTimeSeriesRepo(data))

    def test_empty_paper_ids_returns_empty(self):
        svc = self._make_service({})
        result = svc.detect([], year_start=2010, year_end=2020)
        assert result == []

    def test_single_paper_returns_one_candidate(self):
        data = {"p1": {2019: 5, 2020: 10}}
        svc = self._make_service(data)
        result = svc.detect(["p1"], year_start=2018, year_end=2020)
        assert len(result) == 1
        assert result[0].paper_id == "p1"

    def test_top_k_limits_results(self):
        data = {f"p{i}": {2020: i} for i in range(10)}
        svc = self._make_service(data)
        result = svc.detect(list(data.keys()), year_start=2019, year_end=2020, top_k=3)
        assert len(result) == 3

    def test_top_k_larger_than_papers_returns_all(self):
        data = {"p1": {2020: 5}, "p2": {2020: 3}}
        svc = self._make_service(data)
        result = svc.detect(list(data.keys()), year_start=2019, year_end=2020, top_k=100)
        assert len(result) == 2

    def test_scores_in_unit_interval(self):
        data = {"a": {2019: 1, 2020: 10}, "b": {2019: 5, 2020: 2}, "c": {}}
        svc = self._make_service(data)
        result = svc.detect(list(data.keys()), year_start=2018, year_end=2020)
        for c in result:
            assert 0.0 <= c.burst_score <= 1.0
            assert 0.0 <= c.centrality_shift <= 1.0
            assert 0.0 <= c.breakthrough_score <= 1.0

    def test_sorted_descending_by_score(self):
        data = {f"p{i}": {2019: 0, 2020: i * 5} for i in range(5)}
        svc = self._make_service(data)
        result = svc.detect(list(data.keys()), year_start=2018, year_end=2020)
        scores = [c.breakthrough_score for c in result]
        assert scores == sorted(scores, reverse=True)

    def test_no_citations_all_scores_zero(self):
        data = {"p1": {}, "p2": {}}
        svc = self._make_service(data)
        result = svc.detect(["p1", "p2"], year_start=2018, year_end=2020)
        for c in result:
            assert c.burst_score == 0.0
            assert c.centrality_shift == 0.0
            assert c.breakthrough_score == 0.0

    # --- parameter validation ---

    def test_invalid_alpha_below_zero_raises(self):
        svc = self._make_service({})
        with pytest.raises(ValueError, match="alpha"):
            svc.detect(["p1"], year_start=2010, year_end=2020, alpha=-0.1)

    def test_invalid_alpha_above_one_raises(self):
        svc = self._make_service({})
        with pytest.raises(ValueError, match="alpha"):
            svc.detect(["p1"], year_start=2010, year_end=2020, alpha=1.1)

    def test_alpha_zero_uses_only_shift(self):
        # alpha=0 → breakthrough_score = centrality_shift
        data = {"p1": {2019: 1, 2020: 10}, "p2": {2019: 10, 2020: 1}}
        svc = self._make_service(data)
        result = svc.detect(["p1", "p2"], year_start=2018, year_end=2020, alpha=0.0)
        for c in result:
            assert math.isclose(c.breakthrough_score, c.centrality_shift, abs_tol=1e-9)

    def test_alpha_one_uses_only_burst(self):
        # alpha=1 → breakthrough_score = burst_score
        data = {"p1": {2020: 20}, "p2": {2018: 20}}
        svc = self._make_service(data)
        result = svc.detect(["p1", "p2"], year_start=2018, year_end=2020, alpha=1.0)
        for c in result:
            assert math.isclose(c.breakthrough_score, c.burst_score, abs_tol=1e-9)

    def test_s_le_one_raises(self):
        svc = self._make_service({})
        with pytest.raises(ValueError, match="s"):
            svc.detect(["p1"], year_start=2010, year_end=2020, s=1.0)

    def test_gamma_le_zero_raises(self):
        svc = self._make_service({})
        with pytest.raises(ValueError, match="gamma"):
            svc.detect(["p1"], year_start=2010, year_end=2020, gamma=0.0)

    def test_top_k_zero_raises(self):
        svc = self._make_service({})
        with pytest.raises(ValueError, match="top_k"):
            svc.detect(["p1"], year_start=2010, year_end=2020, top_k=0)

    def test_year_end_before_year_start_raises(self):
        svc = self._make_service({})
        with pytest.raises(ValueError, match="year_end"):
            svc.detect(["p1"], year_start=2020, year_end=2015)

    # --- repository output validation (H2) ---

    def test_negative_count_from_repo_raises(self):
        # Repository returns a negative count → must crash with ValueError, not math error
        data = {"p1": {2020: -1}}
        svc = self._make_service(data)
        with pytest.raises(ValueError, match="negative citation count"):
            svc.detect(["p1"], year_start=2019, year_end=2020)

    def test_negative_count_in_middle_year_raises(self):
        data = {"p1": {2019: 5, 2020: -3, 2021: 2}}
        svc = self._make_service(data)
        with pytest.raises(ValueError, match="negative citation count"):
            svc.detect(["p1"], year_start=2019, year_end=2021)

    def test_multiple_papers_one_bad_count_raises(self):
        data = {"p1": {2020: 5}, "p2": {2020: -2}}
        svc = self._make_service(data)
        with pytest.raises(ValueError, match="negative citation count"):
            svc.detect(["p1", "p2"], year_start=2019, year_end=2020)

    # --- determinism ---

    def test_same_input_same_output(self):
        data = {"p1": {2019: 3, 2020: 7}, "p2": {2019: 8, 2020: 2}}
        svc = self._make_service(data)
        r1 = svc.detect(["p1", "p2"], year_start=2018, year_end=2020)
        r2 = svc.detect(["p1", "p2"], year_start=2018, year_end=2020)
        assert [c.paper_id for c in r1] == [c.paper_id for c in r2]
        assert [c.breakthrough_score for c in r1] == [c.breakthrough_score for c in r2]

    # --- paper absent from repo response treated as zero citations ---

    def test_paper_absent_from_repo_gets_zero_scores(self):
        # Repo returns nothing for "p2"
        data = {"p1": {2020: 10}}
        svc = self._make_service(data)
        result = svc.detect(["p1", "p2"], year_start=2019, year_end=2020)
        p2 = next(c for c in result if c.paper_id == "p2")
        assert p2.burst_score == 0.0
        assert p2.centrality_shift == 0.0
