"""
MethodTrendRepositoryPort
        ↓
TrendMomentumService  (Layer D — Trend Momentum Score, Step 5.2)
        ↓
  score(method_names, year_end, recent_years, ...) → list[MethodTrendScore]

Pipeline:
  [1] Derive window: year_start = year_end − recent_years + 1
  [2] MethodTrendRepositoryPort.get_yearly_usage_counts(method_names, year_start, year_end)
      → per-method yearly paper-usage series
  [3] MethodTrendRepositoryPort.get_venue_distribution(method_names, year_start, year_end)
      → per-method venue → paper count
  [4] For each method:
        cagr             = _compute_cagr(yearly_counts)
        entropy          = _shannon_entropy(venue_dist)
        adoption_velocity= _adoption_velocity(yearly_counts, year_start, year_end)
  [5] Max-normalize each metric independently to [0, 1]
  [6] trend_score = alpha × cagr + beta × entropy + gamma_coef × adoption_velocity
      alpha + beta + gamma_coef must equal 1.0 (enforced by service)
  [7] Sort descending, return top_k MethodTrendScores

Metric definitions:
  CAGR (Compound Annual Growth Rate):
    base = usage count in the first year with data (+ 1 smoothing to handle zeros)
    end  = usage count in the last year with data  (+ 1 smoothing)
    span = years[-1] − years[0]  (actual data span, NOT the window width)
    CAGR = (end / base) ^ (1 / span) − 1
    Negative CAGR is clipped to 0 before normalisation (declining methods excluded).

  Shannon Entropy (venue diversity):
    H = −Σ p_v × log2(p_v)   where p_v = venue_count_v / total_venue_papers
    Higher H → method is adopted across many diverse venues.
    Methods with no venue data receive H = 0.

  Adoption Velocity (linear regression slope):
    Fits a least-squares line through (year, usage_count) pairs.
    Slope > 0 → accelerating adoption; negative slope clipped to 0.
"""

import logging
import math

from aievograph.domain.models import MethodTrendScore
from aievograph.domain.ports.method_trend_repository import MethodTrendRepositoryPort
from aievograph.domain.utils.ranking_utils import normalize_scores
from aievograph.domain.utils.score_utils import combine_scores

logger = logging.getLogger(__name__)

_DEFAULT_ALPHA = 0.4        # weight for CAGR
_DEFAULT_BETA = 0.3         # weight for Shannon entropy
_DEFAULT_GAMMA_COEF = 0.3   # weight for adoption velocity
_DEFAULT_RECENT_YEARS = 5
_DEFAULT_TOP_K = 30

# Plausible publication year bounds (validated in score()).
_MIN_YEAR = 1000
_MAX_YEAR = 2200

# Tolerance for floating-point weight sum check (e.g. 0.4+0.3+0.3 = 0.9999…).
_WEIGHT_SUM_TOL = 1e-9


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _compute_cagr(yearly_counts: dict[int, int]) -> float:
    """Compute CAGR for a method's usage over the analysis window.

    Uses +1 smoothing so that methods with zero usage in the base year still
    receive a meaningful (though large) growth rate when usage appears later.
    The exponent is the actual data span (years[-1] − years[0]), not the
    window width, so sparse data spanning fewer than recent_years is handled
    correctly without systematic under-estimation.
    Negative CAGR (declining usage) is returned as-is; callers clip to 0.

    Args:
        yearly_counts: {year: count} for the analysis window.

    Returns:
        Raw CAGR as a float.  Returns 0.0 if the actual data span < 1 year
        (single data point or empty dict).
    """
    if not yearly_counts:
        return 0.0

    years = sorted(yearly_counts)
    span = years[-1] - years[0]   # actual span between first and last data points
    if span < 1:
        return 0.0

    base_count = yearly_counts[years[0]]
    end_count = yearly_counts[years[-1]]

    # +1 smoothing prevents division-by-zero and reduces instability for sparse methods.
    ratio = (end_count + 1) / (base_count + 1)
    return ratio ** (1.0 / span) - 1.0


def _shannon_entropy(venue_dist: dict[str, int]) -> float:
    """Compute Shannon entropy (bits) of the venue distribution.

    Shannon entropy H ≥ 0 always.  Negative counts violate this invariant and
    indicate upstream data corruption; a ValueError is raised immediately.

    Args:
        venue_dist: {venue_name: paper_count}.  Empty dict → returns 0.0.

    Returns:
        H = −Σ p_v × log2(p_v) in bits.  Returns 0.0 for empty or
        single-venue input.

    Raises:
        ValueError: If any count in venue_dist is negative.
    """
    for venue, count in venue_dist.items():
        if count < 0:
            raise ValueError(
                f"venue_dist contains negative count for venue '{venue}': {count}"
            )

    total = sum(venue_dist.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in venue_dist.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def _adoption_velocity(
    yearly_counts: dict[int, int],
    year_start: int,
    year_end: int,
) -> float:
    """Compute linear-regression slope of yearly usage counts (papers/year).

    Fits OLS on all years in [year_start, year_end], treating missing years as 0.
    Returns the slope (Δusage per year).  Negative slope returned as-is; callers clip.

    Args:
        yearly_counts: {year: count} for the analysis window.
        year_start: First year (inclusive).
        year_end: Last year (inclusive).

    Returns:
        OLS slope as a float.  Returns 0.0 for windows shorter than 2 years.
    """
    years = list(range(year_start, year_end + 1))
    n = len(years)
    if n < 2:
        return 0.0

    counts = [yearly_counts.get(y, 0) for y in years]
    mean_t = sum(years) / n
    mean_y = sum(counts) / n

    numerator = sum((t - mean_t) * (y - mean_y) for t, y in zip(years, counts))
    denominator = sum((t - mean_t) ** 2 for t in years)

    if denominator == 0.0:
        return 0.0
    return numerator / denominator


# ---------------------------------------------------------------------------
# Repository output validation helpers
# ---------------------------------------------------------------------------

def _validate_usage_series(usage_series: dict[str, dict[int, int]]) -> None:
    """Validate that all year keys are int and all counts are non-negative int.

    Raises:
        ValueError: On type mismatch or negative count.
    """
    for name, yearly in usage_series.items():
        for year, count in yearly.items():
            if not isinstance(year, int):
                raise ValueError(
                    f"Repository returned non-integer year key for method '{name}': {year!r}"
                )
            if not isinstance(count, int):
                raise ValueError(
                    f"Repository returned non-integer count for method '{name}' "
                    f"year {year}: {count!r}"
                )
            if count < 0:
                raise ValueError(
                    f"Repository returned negative usage count for method '{name}' "
                    f"year {year}: {count}"
                )


def _validate_venue_dists(venue_dists: dict[str, dict[str, int]]) -> None:
    """Validate that all venue counts are non-negative int.

    Raises:
        ValueError: On type mismatch or negative count.
    """
    for name, dist in venue_dists.items():
        for venue, count in dist.items():
            if not isinstance(count, int):
                raise ValueError(
                    f"Repository returned non-integer venue count for method '{name}' "
                    f"venue '{venue}': {count!r}"
                )
            if count < 0:
                raise ValueError(
                    f"Repository returned negative venue count for method '{name}' "
                    f"venue '{venue}': {count}"
                )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class TrendMomentumService:
    """Compute trend momentum scores for methods in the Method Evolution Graph (Layer D Step 5.2)."""

    def __init__(self, repo: MethodTrendRepositoryPort) -> None:
        self._repo = repo

    def score(
        self,
        method_names: list[str] | None,
        year_end: int,
        recent_years: int = _DEFAULT_RECENT_YEARS,
        top_k: int = _DEFAULT_TOP_K,
        alpha: float = _DEFAULT_ALPHA,
        beta: float = _DEFAULT_BETA,
        gamma_coef: float = _DEFAULT_GAMMA_COEF,
    ) -> list[MethodTrendScore]:
        """Score and rank methods by trend momentum.

        Args:
            method_names: Canonical method names to analyse.
                          Pass None for Discovery mode — all methods in the graph
                          are fetched and ranked without a name filter.
            year_end: Last year of the analysis window (typically current year − 1).
                      Must be in [{_MIN_YEAR}, {_MAX_YEAR}].
            recent_years: Width of the analysis window in years (default 5).
            top_k: Maximum number of results to return.
            alpha: Weight for CAGR in the combined trend_score.
            beta: Weight for Shannon entropy in the combined trend_score.
            gamma_coef: Weight for adoption velocity in the combined trend_score.
                        alpha + beta + gamma_coef must equal 1.0.

        Returns:
            List of MethodTrendScores sorted by trend_score descending.
            All score fields are max-normalised to [0, 1].
            Negative CAGR and negative velocity are clipped to 0 before
            normalisation — declining methods cannot contribute to the ranking.

        Raises:
            ValueError: If recent_years < 1, top_k < 1, any weight < 0,
                        alpha + beta + gamma_coef ≠ 1.0, year_end out of
                        [{_MIN_YEAR}, {_MAX_YEAR}], or the repository returns
                        invalid data (negative counts or wrong types).
        """
        if recent_years < 1:
            raise ValueError(f"recent_years must be >= 1, got {recent_years}")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if alpha < 0 or beta < 0 or gamma_coef < 0:
            raise ValueError("alpha, beta, gamma_coef must all be >= 0")
        weight_sum = alpha + beta + gamma_coef
        if not math.isclose(weight_sum, 1.0, abs_tol=_WEIGHT_SUM_TOL):
            raise ValueError(
                f"alpha + beta + gamma_coef must equal 1.0, got {weight_sum:.10f}"
            )
        if not (_MIN_YEAR <= year_end <= _MAX_YEAR):
            raise ValueError(
                f"year_end must be in [{_MIN_YEAR}, {_MAX_YEAR}], got {year_end}"
            )

        year_start = year_end - recent_years + 1

        # [1] Fetch usage time series and venue distributions.
        # Discovery mode (method_names=None): query all methods without a name filter.
        if method_names is None:
            usage_series = self._repo.get_all_yearly_usage_counts(year_start, year_end)
            venue_dists = self._repo.get_all_venue_distributions(year_start, year_end)
            method_names = list(set(usage_series) | set(venue_dists))
        else:
            if not method_names:
                return []
            usage_series = self._repo.get_yearly_usage_counts(method_names, year_start, year_end)
            venue_dists = self._repo.get_venue_distribution(method_names, year_start, year_end)

        # Validate repository output at the domain boundary.
        _validate_usage_series(usage_series)
        _validate_venue_dists(venue_dists)

        # [2] Compute raw metric values per method.
        raw_cagr: dict[str, float] = {}
        raw_entropy: dict[str, float] = {}
        raw_velocity: dict[str, float] = {}

        for name in method_names:
            yearly = usage_series.get(name, {})
            raw_cagr[name] = max(0.0, _compute_cagr(yearly))
            raw_entropy[name] = _shannon_entropy(venue_dists.get(name, {}))
            raw_velocity[name] = max(0.0, _adoption_velocity(yearly, year_start, year_end))

        # [3] Max-normalize each metric to [0, 1].
        norm_cagr = normalize_scores(raw_cagr)
        norm_entropy = normalize_scores(raw_entropy)
        norm_velocity = normalize_scores(raw_velocity)

        # [4] Combine into trend_score; normalize once more so the weighted sum is in [0, 1].
        norm_trend = combine_scores(
            {"cagr": norm_cagr, "entropy": norm_entropy, "velocity": norm_velocity},
            {"cagr": alpha, "entropy": beta, "velocity": gamma_coef},
            normalize_output=True,
        )

        # [5] Build result objects, sort, return top_k.
        results = [
            MethodTrendScore(
                method_name=name,
                cagr_score=norm_cagr.get(name, 0.0),
                entropy_score=norm_entropy.get(name, 0.0),
                adoption_velocity_score=norm_velocity.get(name, 0.0),
                trend_score=norm_trend.get(name, 0.0),
                yearly_counts=usage_series.get(name, {}),
            )
            for name in method_names
        ]
        results.sort(key=lambda m: (-m.trend_score, m.method_name))

        logger.debug(
            "Trend momentum: %d methods scored (window %d–%d), returning top-%d",
            len(method_names),
            year_start,
            year_end,
            min(top_k, len(results)),
        )
        return results[:top_k]
