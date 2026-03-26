"""Unit tests for TrendMomentumService (Layer D Step 5.2).

Covers:
  - _compute_cagr: C1 CAGR exponent fix, sparse data, edge cases
  - _shannon_entropy: C2 negative count guard, normal, single venue
  - _adoption_velocity: growing, declining, flat, < 2 years
  - score(): happy path, weight sum (H1), year range (H2),
             repo type/negativity validation (H3), weight/param errors
"""

import math
import pytest

from aievograph.domain.ports.method_trend_repository import MethodTrendRepositoryPort
from aievograph.domain.services.trend_momentum_service import (
    TrendMomentumService,
    _adoption_velocity,
    _compute_cagr,
    _shannon_entropy,
)


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------

class StubMethodTrendRepo(MethodTrendRepositoryPort):
    def __init__(
        self,
        usage: dict[str, dict[int, int]] | None = None,
        venues: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self._usage = usage or {}
        self._venues = venues or {}

    def get_yearly_usage_counts(self, method_names, year_start, year_end):
        return self._usage

    def get_venue_distribution(self, method_names, year_start, year_end):
        return self._venues


# ---------------------------------------------------------------------------
# _compute_cagr  (C1: exponent must use actual data span, not window width)
# ---------------------------------------------------------------------------

class TestComputeCagr:
    def test_empty_returns_zero(self):
        assert _compute_cagr({}) == 0.0

    def test_single_year_returns_zero(self):
        # span = 0 → no growth period
        assert _compute_cagr({2020: 5}) == 0.0

    def test_span_one_year(self):
        # {2023: 1, 2024: 10}, span=1 → CAGR = (10+1)/(1+1) - 1 = 4.5
        result = _compute_cagr({2023: 1, 2024: 10})
        assert math.isclose(result, (11 / 2) ** 1 - 1, rel_tol=1e-9)

    def test_span_one_year_not_underestimated_vs_wide_window(self):
        # C1 regression test: sparse data {2023:1, 2024:10} with recent_years=5
        # Old code exponent=1/4 → CAGR≈0.531; correct exponent=1/1 → CAGR=4.5
        result = _compute_cagr({2023: 1, 2024: 10})
        # Must be much larger than old buggy value of ~0.531
        assert result > 2.0

    def test_span_three_years(self):
        # base=2, end=16, span=3 → ratio=17/3, CAGR = (17/3)^(1/3) - 1
        counts = {2017: 2, 2018: 5, 2019: 8, 2020: 16}
        expected = (17 / 3) ** (1 / 3) - 1
        assert math.isclose(_compute_cagr(counts), expected, rel_tol=1e-9)

    def test_zero_base_smoothed(self):
        # base=0 → smoothed to 1; end=9 → smoothed to 10; span=2
        result = _compute_cagr({2018: 0, 2020: 9})
        expected = (10 / 1) ** (1 / 2) - 1
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_declining_returns_negative(self):
        result = _compute_cagr({2018: 10, 2020: 2})
        assert result < 0

    def test_flat_growth_returns_zero(self):
        result = _compute_cagr({2018: 5, 2020: 5})
        # (5+1)/(5+1)^(1/2) - 1 = 1^0.5 - 1 = 0
        assert math.isclose(result, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# _shannon_entropy  (C2: negative count guard)
# ---------------------------------------------------------------------------

class TestShannonEntropy:
    def test_empty_returns_zero(self):
        assert _shannon_entropy({}) == 0.0

    def test_single_venue_returns_zero(self):
        assert _shannon_entropy({"NeurIPS": 10}) == 0.0

    def test_two_equal_venues_returns_one_bit(self):
        h = _shannon_entropy({"A": 5, "B": 5})
        assert math.isclose(h, 1.0, rel_tol=1e-9)

    def test_uniform_four_venues_returns_two_bits(self):
        h = _shannon_entropy({"A": 1, "B": 1, "C": 1, "D": 1})
        assert math.isclose(h, 2.0, rel_tol=1e-9)

    def test_skewed_distribution_less_than_uniform(self):
        skewed = _shannon_entropy({"A": 100, "B": 1, "C": 1, "D": 1})
        uniform = _shannon_entropy({"A": 1, "B": 1, "C": 1, "D": 1})
        assert skewed < uniform

    def test_result_always_non_negative(self):
        h = _shannon_entropy({"X": 3, "Y": 7, "Z": 0})
        assert h >= 0.0

    def test_zero_count_venue_ignored(self):
        h1 = _shannon_entropy({"A": 5, "B": 5})
        h2 = _shannon_entropy({"A": 5, "B": 5, "C": 0})
        assert math.isclose(h1, h2, rel_tol=1e-9)

    def test_negative_count_raises(self):
        with pytest.raises(ValueError, match="negative count"):
            _shannon_entropy({"A": 5, "B": -1})

    def test_all_zero_counts_returns_zero(self):
        assert _shannon_entropy({"A": 0, "B": 0}) == 0.0


# ---------------------------------------------------------------------------
# _adoption_velocity
# ---------------------------------------------------------------------------

class TestAdoptionVelocity:
    def test_single_year_returns_zero(self):
        assert _adoption_velocity({2020: 5}, 2020, 2020) == 0.0

    def test_growing_usage_positive_slope(self):
        counts = {2019: 1, 2020: 2, 2021: 3, 2022: 4}
        slope = _adoption_velocity(counts, 2019, 2022)
        assert slope > 0

    def test_declining_usage_negative_slope(self):
        counts = {2019: 10, 2020: 7, 2021: 4, 2022: 1}
        slope = _adoption_velocity(counts, 2019, 2022)
        assert slope < 0

    def test_flat_usage_zero_slope(self):
        counts = {2019: 5, 2020: 5, 2021: 5, 2022: 5}
        slope = _adoption_velocity(counts, 2019, 2022)
        assert math.isclose(slope, 0.0, abs_tol=1e-9)

    def test_missing_years_treated_as_zero(self):
        # Only 2022 has data; 2020 and 2021 are 0 → counts [0, 0, 10]
        slope = _adoption_velocity({2022: 10}, 2020, 2022)
        assert slope > 0


# ---------------------------------------------------------------------------
# TrendMomentumService.score()
# ---------------------------------------------------------------------------

class TestScore:
    def _svc(self, usage=None, venues=None):
        return TrendMomentumService(StubMethodTrendRepo(usage, venues))

    # --- happy path ---

    def test_empty_method_names_returns_empty(self):
        svc = self._svc()
        assert svc.score([], year_end=2023) == []

    def test_single_method_returns_one_result(self):
        svc = self._svc(usage={"Transformer": {2019: 5, 2023: 20}})
        result = svc.score(["Transformer"], year_end=2023)
        assert len(result) == 1
        assert result[0].method_name == "Transformer"

    def test_scores_in_unit_interval(self):
        usage = {"A": {2019: 1, 2023: 10}, "B": {2019: 8, 2023: 3}, "C": {}}
        svc = self._svc(usage=usage)
        result = svc.score(list(usage.keys()), year_end=2023)
        for r in result:
            assert 0.0 <= r.cagr_score <= 1.0
            assert 0.0 <= r.entropy_score <= 1.0
            assert 0.0 <= r.adoption_velocity_score <= 1.0
            assert 0.0 <= r.trend_score <= 1.0

    def test_sorted_descending(self):
        usage = {f"m{i}": {2019: 0, 2023: i * 3} for i in range(5)}
        svc = self._svc(usage=usage)
        result = svc.score(list(usage.keys()), year_end=2023)
        scores = [r.trend_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_output(self):
        usage = {f"m{i}": {2019: i, 2023: i * 2} for i in range(10)}
        svc = self._svc(usage=usage)
        result = svc.score(list(usage.keys()), year_end=2023, top_k=3)
        assert len(result) == 3

    def test_no_usage_all_scores_zero(self):
        svc = self._svc()
        result = svc.score(["A", "B"], year_end=2023)
        for r in result:
            assert r.cagr_score == 0.0
            assert r.entropy_score == 0.0
            assert r.adoption_velocity_score == 0.0
            assert r.trend_score == 0.0

    def test_deterministic(self):
        usage = {"A": {2019: 3, 2023: 7}, "B": {2019: 8, 2023: 2}}
        svc = self._svc(usage=usage)
        r1 = svc.score(["A", "B"], year_end=2023)
        r2 = svc.score(["A", "B"], year_end=2023)
        assert [r.method_name for r in r1] == [r.method_name for r in r2]
        assert [r.trend_score for r in r1] == [r.trend_score for r in r2]

    # --- H1: weight sum validation ---

    def test_weights_not_summing_to_one_raises(self):
        svc = self._svc()
        with pytest.raises(ValueError, match="1.0"):
            svc.score(["A"], year_end=2023, alpha=0.5, beta=0.3, gamma_coef=0.3)

    def test_weights_summing_to_one_accepted(self):
        svc = self._svc()
        # 0.4 + 0.3 + 0.3 in float is 0.9999… → must still be accepted
        result = svc.score(["A"], year_end=2023, alpha=0.4, beta=0.3, gamma_coef=0.3)
        assert isinstance(result, list)

    def test_all_weight_to_cagr(self):
        usage = {"A": {2019: 1, 2023: 10}, "B": {2019: 10, 2023: 1}}
        svc = self._svc(usage=usage)
        result = svc.score(["A", "B"], year_end=2023, alpha=1.0, beta=0.0, gamma_coef=0.0)
        for r in result:
            assert math.isclose(r.trend_score, r.cagr_score, abs_tol=1e-9)

    def test_negative_weight_raises(self):
        svc = self._svc()
        with pytest.raises(ValueError, match=">="):
            svc.score(["A"], year_end=2023, alpha=-0.1, beta=0.6, gamma_coef=0.5)

    # --- H2: year_end range validation ---

    def test_year_end_below_min_raises(self):
        svc = self._svc()
        with pytest.raises(ValueError, match="year_end"):
            svc.score(["A"], year_end=999)

    def test_year_end_above_max_raises(self):
        svc = self._svc()
        with pytest.raises(ValueError, match="year_end"):
            svc.score(["A"], year_end=3000)

    def test_year_end_at_boundary_accepted(self):
        svc = self._svc()
        result = svc.score(["A"], year_end=1000)
        assert isinstance(result, list)
        result = svc.score(["A"], year_end=2200)
        assert isinstance(result, list)

    # --- H3: repo output validation ---

    def test_negative_usage_count_from_repo_raises(self):
        svc = self._svc(usage={"A": {2023: -1}})
        with pytest.raises(ValueError, match="negative usage count"):
            svc.score(["A"], year_end=2023)

    def test_negative_venue_count_from_repo_raises(self):
        svc = self._svc(venues={"A": {"NeurIPS": -5}})
        with pytest.raises(ValueError, match="negative"):
            svc.score(["A"], year_end=2023)

    def test_string_year_key_from_repo_raises(self):
        svc = self._svc(usage={"A": {"2023": 5}})  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="non-integer year"):
            svc.score(["A"], year_end=2023)

    def test_float_count_from_repo_raises(self):
        svc = self._svc(usage={"A": {2023: 5.0}})  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="non-integer count"):
            svc.score(["A"], year_end=2023)

    # --- other parameter validation ---

    def test_recent_years_zero_raises(self):
        svc = self._svc()
        with pytest.raises(ValueError, match="recent_years"):
            svc.score(["A"], year_end=2023, recent_years=0)

    def test_top_k_zero_raises(self):
        svc = self._svc()
        with pytest.raises(ValueError, match="top_k"):
            svc.score(["A"], year_end=2023, top_k=0)

    # --- method absent from repo gets zero scores ---

    def test_method_absent_from_repo_scores_zero(self):
        svc = self._svc(usage={"A": {2019: 5, 2023: 20}})
        result = svc.score(["A", "missing"], year_end=2023)
        missing = next(r for r in result if r.method_name == "missing")
        assert missing.cagr_score == 0.0
        assert missing.trend_score == 0.0
