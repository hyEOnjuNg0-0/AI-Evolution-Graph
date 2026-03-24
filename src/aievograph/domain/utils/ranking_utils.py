"""Shared utilities for Layer C ranking services."""


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    """Max-normalize a score dict to [0, 1].

    Negative values are clipped to 0 before normalization.
    Returns all-zeros if the maximum is 0 or below.
    """
    max_val = max(scores.values(), default=0.0)
    if max_val <= 0.0:
        return {k: 0.0 for k in scores}
    return {k: max(0.0, v) / max_val for k, v in scores.items()}
