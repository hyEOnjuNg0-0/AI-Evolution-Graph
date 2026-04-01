"""
Breakthrough Detection endpoint (Feature ②).

POST /api/breakthrough
  - Semantically searches for papers in the given field.
  - Runs Kleinberg burst + centrality shift analysis to rank breakthrough papers.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from aievograph.api.dependencies import (
    get_breakthrough_service,
    get_graph_repository,
    get_hybrid_retrieval_service,
)
from aievograph.api.schemas.breakthrough import (
    BreakthroughCandidate,
    BreakthroughRequest,
    BreakthroughResponse,
)
from aievograph.domain.services.breakthrough_detection_service import BreakthroughDetectionService
from aievograph.domain.services.hybrid_retrieval_service import HybridRetrievalService
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

router = APIRouter(prefix="/api/breakthrough", tags=["breakthrough"])
logger = logging.getLogger(__name__)

# Candidate pool size fed into breakthrough detection before top_k filtering.
_CANDIDATE_POOL = 200


@router.post("", response_model=BreakthroughResponse)
def detect_breakthroughs(
    req: BreakthroughRequest,
    retrieval_svc: HybridRetrievalService = Depends(get_hybrid_retrieval_service),
    breakthrough_svc: BreakthroughDetectionService = Depends(get_breakthrough_service),
    graph_repo: Neo4jGraphRepository = Depends(get_graph_repository),
) -> BreakthroughResponse:
    """Detect breakthrough papers in a research field within the given time window.

    Pipeline:
      1. Semantic search finds papers relevant to the `field` query.
      2. BreakthroughDetectionService ranks them by citation-burst + centrality shift.
      3. Results are enriched with paper titles from the graph.
    """
    try:
        # Step 1: Retrieve candidate papers semantically relevant to the field.
        subgraph = retrieval_svc.search(
            query=req.field,
            query_type="semantic",
            top_k=_CANDIDATE_POOL,
            hops=1,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Filter by the requested year window. Papers with no year pass through unconditionally.
    candidate_ids = [
        sp.paper.paper_id
        for sp in subgraph.papers
        if (sp.paper.publication_year is None or sp.paper.publication_year >= req.start_year)
        and (sp.paper.publication_year is None or sp.paper.publication_year <= req.end_year)
    ]

    if not candidate_ids:
        return BreakthroughResponse(candidates=[], total=0)

    try:
        raw_candidates = breakthrough_svc.detect(
            paper_ids=candidate_ids,
            year_start=req.start_year,
            year_end=req.end_year,
            top_k=req.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Enrich candidates with paper metadata.
    paper_cache: dict = {sp.paper.paper_id: sp.paper for sp in subgraph.papers}
    result = []
    for c in raw_candidates:
        paper = paper_cache.get(c.paper_id) or graph_repo.get_paper_by_id(c.paper_id)
        result.append(
            BreakthroughCandidate(
                paper_id=c.paper_id,
                title=paper.title if paper else c.paper_id,
                year=paper.publication_year if paper else None,
                burst_score=c.burst_score,
                centrality_shift=c.centrality_shift,
                composite_score=c.breakthrough_score,
            )
        )

    logger.info(
        "Breakthrough detection field=%r window=%d–%d → %d candidates",
        req.field,
        req.start_year,
        req.end_year,
        len(result),
    )
    return BreakthroughResponse(candidates=result, total=len(result))
