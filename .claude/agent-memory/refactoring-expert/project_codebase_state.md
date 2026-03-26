---
name: AiEvoGraph Codebase State (2026-03-26)
description: Architectural patterns, known duplication points, and layer boundary observations in AiEvoGraph as of Step 5.3 completion and P3/P4 refactoring
type: project
---

Layers A–D (Knowledge Graph, Retrieval, Ranking, Analytical) are fully implemented and tested.
Layer E (Interface) is not yet started.

**Why:** This context is needed to scope refactoring safely — only touch completed lower layers.

**How to apply:** Never suggest changes that touch or assume Layer E logic. All refactoring targets are within `domain/` and `infrastructure/`.

Key structural observations (resolved items marked DONE):
- [DONE] `_MAX_HOPS = 5` — `hybrid_retrieval_service.py` imports `_MAX_HOPS` from `graph_retrieval_service.py`; no duplication.
- [DONE] Cache/HTTP retry logic — extracted into `file_cache.py` and `http_utils.py`; both clients import from those shared modules.
- [DONE] `_record_to_paper()` — `neo4j_vector_repository.py` imports from `neo4j_graph_repository.py`; no duplication.
- [DONE P3] `chunk_size = 500` inline in `semantic_scholar_client._fetch_batch` — extracted to module-level `_S2_CHUNK_SIZE = 500` constant (2026-03-26).
- [DONE P4] `logging.basicConfig(...)` in `scripts/ingest.py` and `scripts/dedup_methods.py` used a `[%(levelname)s]` format inconsistent with `configure_logging()`'s `|` separator format — replaced both with `configure_logging()` calls (2026-03-26).
- `HybridRetrievalService` takes `VectorRetrievalService` (a concrete class) as a constructor argument instead of port abstractions — mild DIP tension; not yet addressed.
- `paper_filter.py` lives in `domain/utils/` (already correct placement).
