"""
EmbeddingPort + PaperEmbeddingRepositoryPort
        ↓
EmbeddingRankingService  (Layer C — Embedding Similarity Ranking, Step 4.2)
        ↓
  rank(query, subgraph)  → list[ScoredPaper]

Pipeline:
  [1] Embed query text via EmbeddingPort
  [2] Fetch stored embeddings for subgraph paper_ids
  [3] Compute cosine similarity between query and each paper embedding
  [4] Fill missing papers (no stored embedding) with score=0.0
  [5] Max-normalize scores to [0, 1]; clip negatives to 0
  [6] Return ScoredPaper list sorted by similarity descending
      paper_id is a deterministic tiebreaker
"""

import logging
import math

from aievograph.domain.models import ScoredPaper, Subgraph
from aievograph.domain.ports.embedding_port import EmbeddingPort
from aievograph.domain.ports.paper_embedding_repository import PaperEmbeddingRepositoryPort
from aievograph.domain.utils.ranking_utils import normalize_scores, sort_scored_papers
from aievograph.domain.utils.validation_utils import validate_non_empty_str

logger = logging.getLogger(__name__)

# Alias for internal use and test imports.
_normalize = normalize_scores


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Raises ValueError if the vectors have different dimensions so that
    embedding model mismatches are caught immediately instead of silently
    producing mathematically incorrect results via zip truncation.
    Returns 0.0 when either vector is the zero vector to avoid division by zero.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Embedding dimension mismatch: query has {len(a)} dims, "
            f"stored vector has {len(b)} dims."
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingRankingService:
    """Rank subgraph papers by semantic similarity to a query (Layer C Step 4.2)."""

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        paper_embedding_repo: PaperEmbeddingRepositoryPort,
    ) -> None:
        self._embedding = embedding_port
        self._paper_embedding_repo = paper_embedding_repo

    def rank(self, query: str, subgraph: Subgraph) -> list[ScoredPaper]:
        """Rank subgraph papers by cosine similarity to the query.

        Args:
            query: Natural-language query text to embed and compare against papers.
            subgraph: Candidate papers from Layer B hybrid retrieval.

        Returns:
            Papers as ScoredPaper list sorted by similarity score descending.
            Papers with no stored embedding receive score=0.0.
            paper_id is a deterministic tiebreaker for equal scores.

        Raises:
            ValueError: If query is empty.
        """
        validate_non_empty_str("query", query)
        if not subgraph.papers:
            return []

        query_embedding = self._embedding.embed(query)
        paper_ids = [sp.paper.paper_id for sp in subgraph.papers]

        stored = self._paper_embedding_repo.get_embeddings(paper_ids)

        # Compute raw cosine similarity; default to 0.0 for papers with no embedding.
        raw_scores: dict[str, float] = {
            pid: _cosine_similarity(query_embedding, stored[pid])
            if pid in stored
            else 0.0
            for pid in paper_ids
        }

        normalized = _normalize(raw_scores)

        papers_map = {sp.paper.paper_id: sp.paper for sp in subgraph.papers}
        result = [
            ScoredPaper(paper=papers_map[pid], score=normalized[pid])
            for pid in paper_ids
        ]
        sort_scored_papers(result)

        if result:
            logger.debug(
                "Embedding ranking: %d papers → top=%s (score=%.4f)",
                len(result),
                result[0].paper.paper_id,
                result[0].score,
            )
        return result
