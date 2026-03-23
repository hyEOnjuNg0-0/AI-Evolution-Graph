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
6. A name that adds a modifier (dimension, direction, strategy prefix, scope qualifier, \
   etc.) to a general term describes a MORE SPECIFIC concept — do NOT merge it into the \
   general term. If names differ in specificity, keep each as its own group. \
   Examples of incorrect merges: "2D Convolution"→"Convolution", \
   "1-vs-All Classification"→"Classification", "Bidirectional LSTM"→"LSTM".
7. DEFAULT TO SEPARATE. Only merge when you are highly confident the names refer to \
   the exact same concept. If there is any doubt, return each name as its own group \
   with an empty variants list. A wrong merge permanently destroys information; \
   a missed merge can be fixed later.

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


def _trigrams(key: str) -> set[str]:
    """Return the set of character trigrams for a normalized key.

    Keys shorter than 3 characters (including the empty string produced by
    _key() for names that contain no alphanumeric characters) are returned as
    a single token so they can still be matched against each other via the
    trigram index.  Empty-key names will share the "" token, causing them to
    become candidate pairs; SequenceMatcher("", "").ratio() == 1.0, so they
    will be merged — an expected and acceptable outcome for names that carry
    no alphanumeric information.
    """
    if len(key) < 3:
        return {key}
    return {key[i : i + 3] for i in range(len(key) - 2)}


def _find_candidate_clusters(
    names: list[str], threshold: float = 0.90, min_key_len: int = 5
) -> list[list[str]]:
    """Group names whose normalized string similarity exceeds `threshold`.

    Uses a trigram inverted index to skip pairs with no shared trigrams,
    reducing SequenceMatcher calls from O(n²) to O(candidate pairs) in the
    typical case where names are diverse.  Worst-case complexity remains
    O(n²): if all n names share a common trigram (e.g. all contain "bert"),
    candidate_pairs grows to O(n²) and the trigram index adds overhead on
    top of the O(n²) comparisons.  Union-find captures transitive similarity
    chains.  Only clusters with 2+ members are returned.

    Short keys (len < min_key_len) are excluded from fuzzy comparison to
    prevent short acronyms (e.g. "MACE", "RACE") from being falsely clustered
    due to incidental character overlap.  Exact-key duplicates (ratio == 1.0)
    are still captured by the trigram index regardless of key length.
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

    # Step 1: build trigram inverted index
    trigram_index: dict[str, set[int]] = defaultdict(set)
    key_trigrams: list[set[str]] = []
    for i, k in enumerate(keys):
        tg = _trigrams(k)
        key_trigrams.append(tg)
        for t in tg:
            trigram_index[t].add(i)

    # Step 2: collect candidate pairs that share at least one trigram
    candidate_pairs: set[tuple[int, int]] = set()
    for i in range(n):
        for t in key_trigrams[i]:
            for j in trigram_index[t]:
                if j > i:
                    candidate_pairs.add((i, j))

    # Step 3: apply SequenceMatcher only on candidate pairs.
    # Skip pairs where either key is shorter than min_key_len to avoid false
    # positives from short acronyms; exact matches (ratio == 1.0) for those
    # keys are already handled via the trigram index above.
    for i, j in candidate_pairs:
        if len(keys[i]) < min_key_len or len(keys[j]) < min_key_len:
            continue
        ratio = SequenceMatcher(None, keys[i], keys[j]).ratio()
        if ratio >= threshold:
            union(i, j)

    # Step 4: collect clusters
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

    _BATCH_SIZE = 50

    def _llm_normalize(self, clusters: list[list[str]]) -> NormalizationMap:
        mapping: dict[str, str] = {}
        total = len(clusters)
        for batch_start in range(0, total, self._BATCH_SIZE):
            batch = clusters[batch_start : batch_start + self._BATCH_SIZE]
            batch_end = min(batch_start + self._BATCH_SIZE, total)
            logger.info(
                "LLM normalization batch %d-%d / %d clusters.",
                batch_start + 1, batch_end, total,
            )
            partial = self._llm_normalize_batch(batch)
            mapping.update(partial)

        logger.debug("Built normalization mapping with %d entries.", len(mapping))
        return NormalizationMap(mapping=mapping)

    def _llm_normalize_batch(self, clusters: list[list[str]]) -> dict[str, str]:
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
            logger.warning("LLM returned no parsed result for normalization batch.")
            return {}

        return {
            variant: group.canonical
            for group in parsed.groups
            for variant in group.variants
            if variant != group.canonical
        }
