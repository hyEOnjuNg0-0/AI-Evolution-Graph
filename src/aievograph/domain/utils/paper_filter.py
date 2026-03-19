import math
from collections import defaultdict

from aievograph.domain.models import Paper


def compute_citation_thresholds(
    papers: list[Paper],
    top_percent: float = 0.20,
) -> dict[int, int]:
    """Compute per-year citation count threshold for the top N% of papers.

    Returns a mapping of year -> minimum citation count to be in the top tier.
    """
    by_year: dict[int, list[int]] = defaultdict(list)
    for p in papers:
        by_year[p.publication_year].append(p.citation_count)

    thresholds: dict[int, int] = {}
    for year, counts in by_year.items():
        sorted_counts = sorted(counts, reverse=True)
        cutoff_idx = max(1, math.ceil(len(sorted_counts) * top_percent)) - 1
        thresholds[year] = sorted_counts[cutoff_idx]

    return thresholds


def filter_top_cited(
    papers: list[Paper],
    top_percent: float = 0.20,
) -> list[Paper]:
    """Keep only papers whose citation count is >= the per-year top-percent threshold."""
    thresholds = compute_citation_thresholds(papers, top_percent)
    return [
        p
        for p in papers
        if p.citation_count >= thresholds[p.publication_year]
    ]
