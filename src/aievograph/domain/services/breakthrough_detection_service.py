"""
CitationTimeSeriesRepositoryPort
        ↓
BreakthroughDetectionService  (Layer D — Breakthrough Detection, Step 5.1)
        ↓
  detect(paper_ids, year_start, year_end, top_k, alpha) → list[BreakthroughCandidate]

Pipeline:
  [1] CitationTimeSeriesRepositoryPort.get_yearly_citation_counts(paper_ids, year_start, year_end)
      → per-paper yearly citation series
  [2] For each paper: Kleinberg 2-state burst score (citation burst intensity)
  [3] For each paper: centrality shift (citation-rate gain, recent half vs past half of window)
  [4] Max-normalize burst_scores and centrality_shifts across all papers to [0, 1]
  [5] breakthrough_score = alpha × burst_score + (1 − alpha) × centrality_shift
  [6] Sort descending, return top_k BreakthroughCandidates

Kleinberg burst detection (2-state Viterbi):
  Background rate q₀ = total_citations / window_years
  Burst rate      q₁ = s × q₀   (default s=2.0)
  Emission cost   = −ln P(count | Poisson(rate))
  Transition cost = γ × ln(max(total_citations, 2))  for each step UP in state
                  = 0  for steps DOWN (Kleinberg's asymmetric cost)
  Viterbi DP assigns each year a state {0, 1}; burst_score = recency-weighted
  fraction of years assigned to state 1.
"""

import logging
import math

from aievograph.domain.models import BreakthroughCandidate
from aievograph.domain.ports.citation_time_series_repository import (
    CitationTimeSeriesRepositoryPort,
)
from aievograph.domain.utils.ranking_utils import normalize_scores

logger = logging.getLogger(__name__)

_DEFAULT_ALPHA = 0.5   # weight for burst_score vs centrality_shift
_DEFAULT_TOP_K = 20
_DEFAULT_S = 2.0       # burst rate multiplier (q₁ = s × q₀)
_DEFAULT_GAMMA = 1.0   # Kleinberg transition cost coefficient


# ---------------------------------------------------------------------------
# Kleinberg helpers
# ---------------------------------------------------------------------------

def _poisson_neg_log_prob(k: int, lam: float) -> float:
    """Negative log-likelihood of Poisson(lam) evaluated at k.

    Uses math.lgamma for the factorial term so it is safe for large k.
    Returns 0.0 when lam=0 and k=0 (consistent with convention), or
    a very large number when lam=0 and k>0.

    Raises:
        ValueError: If k is negative (citation counts must be non-negative).
    """
    if k < 0:
        raise ValueError(f"k must be a non-negative integer, got {k}")
    if lam <= 0.0:
        return 0.0 if k == 0 else 1e18
    return lam - k * math.log(lam) + math.lgamma(k + 1)


def _viterbi_states(
    counts: list[int],
    q0: float,
    s: float,
    gamma: float,
) -> list[int]:
    """Run 2-state Viterbi on a citation count sequence.

    State 0: background rate q0
    State 1: burst rate s × q0

    Transition cost: γ × ln(max(n, 2)) per step UP; 0 for steps DOWN.
    Initial state is assumed to be 0 (background).

    Args:
        counts: Citation counts per year (ordered).
        q0: Background citation rate (total / years).
        s: Burst multiplier.
        gamma: Kleinberg transition cost coefficient.

    Returns:
        List of state assignments (0 or 1) for each year.
    """
    T = len(counts)
    if T == 0:
        return []

    n_total = sum(counts)
    rates = [q0, s * q0]
    tau = gamma * math.log(max(n_total, 2))
    INF = 1e18
    K = 2

    # dp[k]: minimum cost to be in state k at the current step
    # prev[t][k]: previous state that led to minimum cost at time t in state k
    dp = [0.0] * K
    # Cost to start in state j from implied initial state 0
    for j in range(K):
        dp[j] = max(0, j) * tau + _poisson_neg_log_prob(counts[0], rates[j])

    prev: list[list[int]] = [[-1] * K for _ in range(T)]

    for t in range(1, T):
        new_dp = [INF] * K
        for j in range(K):
            emit = _poisson_neg_log_prob(counts[t], rates[j])
            for i in range(K):
                trans = max(0, j - i) * tau  # free to go down, costly to go up
                cost = dp[i] + trans + emit
                if cost < new_dp[j]:
                    new_dp[j] = cost
                    prev[t][j] = i
        dp = new_dp

    # Backtrack from the lowest-cost final state
    states = [0] * T
    states[T - 1] = 0 if dp[0] <= dp[1] else 1
    for t in range(T - 2, -1, -1):
        states[t] = prev[t + 1][states[t + 1]]

    return states


def _kleinberg_burst_score(
    yearly_counts: dict[int, int],
    year_start: int,
    year_end: int,
    s: float,
    gamma: float,
) -> float:
    """Compute raw Kleinberg burst score for a single paper.

    Score = recency-weighted fraction of years assigned to burst state (state 1).
    Later years receive a linearly increasing weight so recent bursts count more.

    Returns 0.0 when there are no citations or only one year in the window.
    """
    years = list(range(year_start, year_end + 1))
    T = len(years)
    if T == 0:
        return 0.0

    counts = [yearly_counts.get(y, 0) for y in years]
    n_total = sum(counts)
    if n_total == 0:
        return 0.0

    q0 = n_total / T
    states = _viterbi_states(counts, q0, s, gamma)

    # Recency weight: w(t) = 1 + t/(T-1), t ∈ {0, …, T-1}
    # Rationale: linear ramp doubles the weight of the most recent year relative
    # to the oldest, making a burst in year T-1 twice as impactful as an equal
    # burst in year 0.  The ramp is anchored at 1.0 so that even the oldest
    # year contributes positively (avoiding a zero-weight dead zone).
    # Range: [1.0, 2.0] — chosen to be narrow enough to preserve the Viterbi
    # state signal while still rewarding recency.
    recency_weights = [1.0 + t / max(T - 1, 1) for t in range(T)]
    burst_score = sum(
        w for st, w in zip(states, recency_weights) if st == 1
    )
    max_possible = sum(recency_weights)
    return burst_score / max_possible if max_possible > 0 else 0.0


def _centrality_shift_score(
    yearly_counts: dict[int, int],
    year_start: int,
    year_end: int,
) -> float:
    """Compute raw centrality shift: recent-half citation rate minus past-half rate.

    Splits the window at the midpoint. Rate = total_citations / window_years.
    Returns the difference (can be negative if the paper lost citations).
    """
    years = list(range(year_start, year_end + 1))
    T = len(years)
    if T < 2:
        return 0.0

    mid = T // 2
    past_years = years[:mid]
    recent_years = years[mid:]

    past_rate = sum(yearly_counts.get(y, 0) for y in past_years) / len(past_years)
    recent_rate = sum(yearly_counts.get(y, 0) for y in recent_years) / len(recent_years)
    return recent_rate - past_rate


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BreakthroughDetectionService:
    """Detect breakthrough papers via citation burst and centrality shift (Layer D Step 5.1)."""

    def __init__(self, repo: CitationTimeSeriesRepositoryPort) -> None:
        self._repo = repo

    def detect(
        self,
        paper_ids: list[str],
        year_start: int,
        year_end: int,
        top_k: int = _DEFAULT_TOP_K,
        alpha: float = _DEFAULT_ALPHA,
        s: float = _DEFAULT_S,
        gamma: float = _DEFAULT_GAMMA,
    ) -> list[BreakthroughCandidate]:
        """Score and rank breakthrough candidates.

        Args:
            paper_ids: Papers to analyse (typically all papers in the citation graph).
            year_start: First year of the analysis window (inclusive).
            year_end: Last year of the analysis window (inclusive).
            top_k: Maximum number of candidates to return.
            alpha: Burst-score weight in [0.0, 1.0].
                   alpha=1.0 → rank purely by citation-burst intensity.
                   alpha=0.0 → rank purely by centrality shift (recent vs past half).
                   alpha=0.5 (default) → equal blend of both signals.
            s: Kleinberg burst-rate multiplier (q₁ = s × q₀); must be > 1.
               Higher s demands a stronger citation spike to enter burst state.
            gamma: Kleinberg transition cost coefficient; must be > 0.
               Higher gamma penalises switching between states more heavily,
               producing smoother (fewer, longer) burst segments.

        Returns:
            List of BreakthroughCandidates sorted by breakthrough_score descending.
            All score fields are max-normalised to [0, 1].
            Papers with no citations receive score 0.0 for both signals.
            Negative centrality shifts (papers that lost citations) are clipped to
            0.0 before normalisation — they cannot contribute to breakthrough ranking.

        Raises:
            ValueError: If alpha outside [0,1], s <= 1, gamma <= 0, top_k < 1,
                        year_end < year_start, or the repository returns a negative
                        citation count (indicates upstream data corruption).
        """
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be in [0.0, 1.0], got {alpha}")
        if s <= 1.0:
            raise ValueError(f"s (burst multiplier) must be > 1, got {s}")
        if gamma <= 0.0:
            raise ValueError(f"gamma must be > 0, got {gamma}")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if year_end < year_start:
            raise ValueError(f"year_end ({year_end}) must be >= year_start ({year_start})")
        if not paper_ids:
            return []

        # [1] Fetch citation time series for all candidate papers.
        time_series = self._repo.get_yearly_citation_counts(paper_ids, year_start, year_end)

        # Validate repository output — negative counts indicate a data corruption bug.
        for pid, yearly in time_series.items():
            for year, count in yearly.items():
                if count < 0:
                    raise ValueError(
                        f"Repository returned negative citation count for paper '{pid}'"
                        f" in year {year}: {count}"
                    )

        # [2] Compute raw burst and shift scores per paper.
        raw_burst: dict[str, float] = {}
        raw_shift: dict[str, float] = {}

        for pid in paper_ids:
            yearly = time_series.get(pid, {})
            raw_burst[pid] = _kleinberg_burst_score(yearly, year_start, year_end, s, gamma)
            raw_shift[pid] = _centrality_shift_score(yearly, year_start, year_end)

        # [3] Clip negative shifts (papers that lost citations are not breakthroughs).
        clipped_shift: dict[str, float] = {pid: max(0.0, v) for pid, v in raw_shift.items()}

        # [4] Max-normalize both score dicts to [0, 1].
        norm_burst = normalize_scores(raw_burst)
        norm_shift = normalize_scores(clipped_shift)

        # [5] Combined breakthrough score.
        combined: dict[str, float] = {
            pid: alpha * norm_burst.get(pid, 0.0) + (1.0 - alpha) * norm_shift.get(pid, 0.0)
            for pid in paper_ids
        }

        # [6] Build candidates, sort descending, return top_k.
        candidates = [
            BreakthroughCandidate(
                paper_id=pid,
                burst_score=norm_burst.get(pid, 0.0),
                centrality_shift=norm_shift.get(pid, 0.0),
                breakthrough_score=combined[pid],
            )
            for pid in paper_ids
        ]
        candidates.sort(key=lambda c: (-c.breakthrough_score, c.paper_id))

        logger.debug(
            "Breakthrough detection: %d papers → top-%d (window %d–%d)",
            len(paper_ids),
            min(top_k, len(candidates)),
            year_start,
            year_end,
        )
        return candidates[:top_k]
