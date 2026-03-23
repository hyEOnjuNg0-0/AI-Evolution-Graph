"""
VectorRetrievalService
    ↓
  search(query)            → embed query → similarity_search → list[ScoredPaper]
  embed_and_store_papers() → embed_batch → store_embedding per paper
"""

import logging

from aievograph.domain.models import Paper, ScoredPaper
from aievograph.domain.ports.embedding_port import EmbeddingPort
from aievograph.domain.ports.vector_repository import VectorRepositoryPort

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 64
# text-embedding-3-small supports up to 8191 tokens (~4 chars/token → 32 000 chars is a safe ceiling)
_MAX_TEXT_CHARS = 32_000


class VectorRetrievalService:
    """Orchestrates embedding generation and semantic similarity search (Layer B Step 3.1)."""

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        vector_repo: VectorRepositoryPort,
    ) -> None:
        self._embedding = embedding_port
        self._vector_repo = vector_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> list[ScoredPaper]:
        """Embed query text and return top-k semantically similar papers."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")
        query_embedding = self._embedding.embed(query)
        results = self._vector_repo.similarity_search(query_embedding, top_k)
        logger.info("Vector search returned %d results for query.", len(results))
        return results

    def embed_and_store_papers(
        self, papers: list[Paper], batch_size: int = _DEFAULT_BATCH_SIZE
    ) -> None:
        """Generate embeddings in batches and persist them on Paper nodes."""
        if batch_size <= 0:
            raise ValueError(f"batch_size must be a positive integer, got {batch_size}")

        # Deduplicate by paper_id while preserving order
        seen: set[str] = set()
        unique_papers: list[Paper] = []
        for p in papers:
            if p.paper_id not in seen:
                seen.add(p.paper_id)
                unique_papers.append(p)

        self._vector_repo.create_vector_index()

        if not unique_papers:
            return

        total = len(unique_papers)
        for start in range(0, total, batch_size):
            batch = unique_papers[start : start + batch_size]
            texts = [self._paper_to_text(p) for p in batch]
            embeddings = self._embedding.embed_batch(texts)
            # Guard against API returning fewer embeddings than requested
            if len(embeddings) != len(batch):
                raise RuntimeError(
                    f"Embedding count mismatch: expected {len(batch)}, got {len(embeddings)}"
                )
            for paper, embedding in zip(batch, embeddings):
                self._vector_repo.store_embedding(paper.paper_id, embedding)
            end = min(start + batch_size, total)
            logger.info("Stored embeddings for papers %d–%d / %d.", start + 1, end, total)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _paper_to_text(paper: Paper) -> str:
        """Build the text used for embedding: title + abstract (if available).

        Truncates to _MAX_TEXT_CHARS to stay within text-embedding-3-small's 8191-token limit.
        """
        parts = [paper.title]
        if paper.abstract:
            parts.append(paper.abstract)
        return " ".join(parts)[:_MAX_TEXT_CHARS]
