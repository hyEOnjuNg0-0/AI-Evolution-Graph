---
name: AiEvoGraph Codebase State (2026-03-19)
description: Architectural patterns, known duplication points, and layer boundary observations in AiEvoGraph as of Step 3.3 completion
type: project
---

Layer A (Knowledge Graph) and Layer B (Retrieval) are fully implemented and tested.
Layers C, D, E are not yet started.

**Why:** This context is needed to scope refactoring safely — only touch completed lower layers.

**How to apply:** Never suggest changes that touch or assume Layer C–E logic. All refactoring targets are within `domain/` and `infrastructure/`.

Key structural observations:
- `_MAX_HOPS = 5` is defined independently in both `graph_retrieval_service.py` and `hybrid_retrieval_service.py` — the most significant duplication point.
- Cache read/write logic (`_read_cache`, `_write_cache`, checkpoint save/load) is duplicated between `arxiv_client.py` and `semantic_scholar_client.py`.
- HTTP retry logic (exponential backoff on 429/5xx) is similarly duplicated: `_get_with_retry` / `_post_with_retry` in `SemanticScholarClient`, `_s2_post_with_retry` in `ArxivClient`.
- `_record_to_paper()` is defined separately in both `neo4j_graph_repository.py` and `neo4j_vector_repository.py` — near-identical logic.
- `HybridRetrievalService` takes `VectorRetrievalService` (a concrete class) as a constructor argument instead of the `VectorRepositoryPort` + `EmbeddingPort` abstractions — mild DIP tension (concrete service dependency rather than port dependency).
- `paper_filter.py` lives in `domain/services/` but is a pure utility function with no state or port dependency — could be argued to belong in a `domain/utils/` module.
- `ArxivClient` imports `filter_top_cited` from `domain/services/paper_filter.py` — infrastructure importing from domain services is acceptable per Clean Architecture (outer depends on inner), but this creates a concrete coupling to a pure utility.
