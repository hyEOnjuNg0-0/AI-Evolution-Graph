"""Shared score combination utilities for Layer C and Layer D services."""

import logging

from aievograph.domain.utils.ranking_utils import normalize_scores

logger = logging.getLogger(__name__)


def combine_scores(
    score_dicts: dict[str, dict[str, float]],
    weights: dict[str, float],
    *,
    normalize_output: bool = True,
) -> dict[str, float]:
    """Normalize each score dict independently, then combine with weights.

    Each score dict is max-normalized to [0, 1] before weighting so that
    different-scale metrics are comparable.

    Args:
        score_dicts: mapping of name -> {entity_id: raw_score}
        weights: mapping of name -> weight (must match keys of score_dicts)
        normalize_output: if True, apply a final normalize_scores() on the
            weighted-sum result so the output is also in [0, 1].

    Returns:
        dict mapping entity_id -> combined_score
    """
    normalized = {name: normalize_scores(scores) for name, scores in score_dicts.items()}

    all_ids: set[str] = set()
    for scores_dict in normalized.values():
        all_ids.update(scores_dict.keys())

    combined: dict[str, float] = {
        eid: sum(
            normalized[name].get(eid, 0.0) * weight
            for name, weight in weights.items()
        )
        for eid in all_ids
    }

    return normalize_scores(combined) if normalize_output else combined
