"""Shared utilities for Layer C ranking services."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aievograph.domain.models import Paper, ScoredPaper, Subgraph

logger = logging.getLogger(__name__)


def build_papers_map(subgraph: "Subgraph") -> "dict[str, Paper]":
    """Build a {paper_id: Paper} lookup map from a Subgraph's scored papers.

    Used by ranking services to resolve paper_id references back to Paper objects
    when constructing ScoredPaper results.
    """
    return {sp.paper.paper_id: sp.paper for sp in subgraph.papers}


def sort_scored_papers(papers: "list[ScoredPaper]") -> "list[ScoredPaper]":
    """Sort a ScoredPaper list by score descending, paper_id ascending as tiebreaker.

    Mutates the list in-place (consistent with how callers use .sort()) and
    also returns it for convenience.
    """
    papers.sort(key=lambda sp: (-sp.score, sp.paper.paper_id))
    return papers


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    """Max-normalize a score dict to [0, 1].

    Negative values are clipped to 0 before normalization.
    Returns all-zeros if the maximum is 0 or below.

    Warns when negative values are found — they indicate a possible upstream
    computation error and should not occur in normal operation.
    """
    negative_keys = [k for k, v in scores.items() if v < 0]
    if negative_keys:
        logger.warning(
            "normalize_scores: %d negative value(s) clipped to 0.0 — possible upstream error. "
            "Keys: %s%s",
            len(negative_keys),
            negative_keys[:5],
            " …" if len(negative_keys) > 5 else "",
        )

    max_val = max(scores.values(), default=0.0)
    if max_val <= 0.0:
        return {k: 0.0 for k in scores}
    return {k: max(0.0, v) / max_val for k, v in scores.items()}
