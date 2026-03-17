"""LLM-based entity normalizer: string-similarity clustering + GPT-4o judgment."""

import logging
import re
from collections import defaultdict
from difflib import SequenceMatcher

from openai import OpenAI
from pydantic import BaseModel

from aievograph.domain.models import Method, NormalizationMap
from aievograph.domain.ports.entity_normalizer import EntityNormalizerPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM output schema (internal)
# ---------------------------------------------------------------------------

class _NormalizationGroup(BaseModel):
    canonical: str
    variants: list[str]  # names that should map to canonical (may include canonical itself)


class _NormalizationResponse(BaseModel):
    groups: list[_NormalizationGroup]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an AI research knowledge graph expert. Your task is to identify which method \
names refer to the same concept and determine the single canonical name for each group.

RULES:
1. Only merge names that clearly refer to the SAME method or model.
2. Case-only differences (e.g., "bert" vs "BERT") must always be merged.
3. Version/size variants (e.g., "BERT-large", "GPT-3") should be merged into the base \
   name ONLY when the abstract clearly treats them as the same concept; otherwise keep \
   them separate.
4. The canonical name should be the most widely recognized, official form.
5. If all names in a cluster are actually DIFFERENT methods, return each as its own \
   group with an empty variants list.

EXAMPLE:
Input clusters: [["BERT", "bert", "Bert"], ["GPT-3", "GPT3", "gpt-3"]]
Output:
{
  "groups": [
    {"canonical": "BERT", "variants": ["bert", "Bert"]},
    {"canonical": "GPT-3", "variants": ["GPT3", "gpt-3"]}
  ]
}
"""


def _build_prompt(clusters: list[list[str]]) -> str:
    cluster_str = "\n".join(
        f"  Cluster {i + 1}: {names}" for i, names in enumerate(clusters)
    )
    return (
        "Determine the canonical name and variant mappings for each cluster below.\n\n"
        f"Input clusters:\n{cluster_str}"
    )


# ---------------------------------------------------------------------------
# String-similarity clustering (no LLM)
# ---------------------------------------------------------------------------

def _key(name: str) -> str:
    """Normalize a name to a comparable key (lowercase, alphanumeric only)."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find_candidate_clusters(
    names: list[str], threshold: float = 0.82
) -> list[list[str]]:
    """Group names whose normalized string similarity exceeds `threshold`.

    Uses union-find so that transitive similarity chains are captured.
    Only clusters with 2+ members are returned.
    """
    n = len(names)
    if n == 0:
        return []

    keys = [_key(name) for name in names]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            ratio = SequenceMatcher(None, keys[i], keys[j]).ratio()
            if ratio >= threshold:
                union(i, j)

    groups: dict[int, list[str]] = defaultdict(list)
    for i, name in enumerate(names):
        groups[find(i)].append(name)

    return [g for g in groups.values() if len(g) > 1]


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

class LLMEntityNormalizer(EntityNormalizerPort):
    """Normalize Method entities via string-similarity pre-clustering + LLM judgment."""

    def __init__(self, client: OpenAI, model: str = "gpt-4o") -> None:
        self._client = client
        self._model = model

    def normalize(self, methods: list[Method]) -> NormalizationMap:
        clusters = _find_candidate_clusters([m.name for m in methods])
        if not clusters:
            logger.debug("No similar method name clusters found; skipping LLM call.")
            return NormalizationMap()

        logger.info("Sending %d candidate clusters to LLM for normalization.", len(clusters))
        return self._llm_normalize(clusters)

    def _llm_normalize(self, clusters: list[list[str]]) -> NormalizationMap:
        response = self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(clusters)},
            ],
            response_format=_NormalizationResponse,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            logger.warning("LLM returned no parsed result for normalization.")
            return NormalizationMap()

        mapping: dict[str, str] = {}
        for group in parsed.groups:
            for variant in group.variants:
                if variant != group.canonical:
                    mapping[variant] = group.canonical

        logger.debug("Built normalization mapping with %d entries.", len(mapping))
        return NormalizationMap(mapping=mapping)
