"""
Research Lineage Exploration endpoint (Feature ①).

POST /api/lineage
  - Runs hybrid retrieval (semantic + graph) seeded by the query text.
  - Returns the top-k papers and the citation edges among them.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from aievograph.api.dependencies import get_graph_repository, get_hybrid_retrieval_service
from aievograph.api.schemas.lineage import CitationEdge, LineageRequest, LineageResponse, PaperNode
from aievograph.domain.services.hybrid_retrieval_service import HybridRetrievalService
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

router = APIRouter(prefix="/api/lineage", tags=["lineage"])
logger = logging.getLogger(__name__)


@router.post("", response_model=LineageResponse)
def explore_lineage(
    req: LineageRequest,
    retrieval_svc: HybridRetrievalService = Depends(get_hybrid_retrieval_service),
    graph_repo: Neo4jGraphRepository = Depends(get_graph_repository),
) -> LineageResponse:
    """Return a subgraph of papers related to the seed query with citation edges.

    The seed can be a keyword query or a Semantic Scholar paper ID.
    Results are scored by α×semantic_similarity + β×graph_proximity.
    """
    try:
        subgraph = retrieval_svc.search(
            query=req.seed,
            query_type=req.query_type,
            top_k=req.top_k,
            hops=req.hop_depth,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    paper_ids = {sp.paper.paper_id for sp in subgraph.papers}

    # Apply optional year filters. Papers with no year pass through unconditionally.
    scored_papers = [
        sp for sp in subgraph.papers
        if (req.start_year is None or sp.paper.publication_year is None or sp.paper.publication_year >= req.start_year)
        and (req.end_year is None or sp.paper.publication_year is None or sp.paper.publication_year <= req.end_year)
    ]

    nodes = [
        PaperNode(
            paper_id=sp.paper.paper_id,
            title=sp.paper.title,
            year=sp.paper.publication_year,
            authors=[a.name for a in sp.paper.authors],
            citation_count=sp.paper.citation_count,
            score=sp.score,
        )
        for sp in scored_papers
    ]

    # Collect citation edges within the filtered paper set.
    result_ids = {n.paper_id for n in nodes}
    edges: list[CitationEdge] = []
    for node in nodes:
        try:
            neighbors = graph_repo.get_citation_neighborhood(node.paper_id, hops=1)
        except Exception:
            logger.warning("Failed to fetch neighbors for %s", node.paper_id)
            continue
        for neighbor in neighbors:
            if neighbor.paper_id in result_ids:
                edges.append(CitationEdge(source_id=node.paper_id, target_id=neighbor.paper_id))

    # Deduplicate directed edges; A→B and B→A are distinct citation relationships.
    seen: set[tuple[str, str]] = set()
    unique_edges = []
    for e in edges:
        key = (e.source_id, e.target_id)
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    logger.info("Lineage query=%r → %d papers, %d edges", req.seed, len(nodes), len(unique_edges))
    return LineageResponse(papers=nodes, edges=unique_edges, total=len(nodes))
