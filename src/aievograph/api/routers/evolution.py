"""
Method Evolution Path endpoint (Feature ③ — Search mode).

POST /api/evolution
  - Fuzzy-matches a method name and traces its evolution path through the
    Method Evolution Graph (IMPROVES / EXTENDS / REPLACES relations).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from aievograph.api.dependencies import (
    get_breakthrough_service,
    get_evolution_path_service,
    get_graph_repository,
    get_trend_service,
)
from aievograph.api.schemas.evolution import EvolutionRequest, EvolutionResponse, EvolutionStep
from aievograph.domain.services.breakthrough_detection_service import BreakthroughDetectionService
from aievograph.domain.services.evolution_path_service import EvolutionPathService
from aievograph.domain.services.trend_momentum_service import TrendMomentumService
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

router = APIRouter(prefix="/api/evolution", tags=["evolution"])
logger = logging.getLogger(__name__)

# Limit breakthrough paper IDs forwarded to EvolutionPathService.
_BREAKTHROUGH_PAPER_LIMIT = 1_000


@router.post("", response_model=EvolutionResponse)
def trace_evolution(
    req: EvolutionRequest,
    graph_repo: Neo4jGraphRepository = Depends(get_graph_repository),
    trend_svc: TrendMomentumService = Depends(get_trend_service),
    breakthrough_svc: BreakthroughDetectionService = Depends(get_breakthrough_service),
    evolution_svc: EvolutionPathService = Depends(get_evolution_path_service),
) -> EvolutionResponse:
    """Trace the evolution path of a method.

    Pipeline:
      1. Fuzzy-match method_name against all known method names.
      2. TrendMomentumService scores matched methods.
      3. EvolutionPathService extracts the research-lineage DAG.
    """
    recent_years = req.end_year - req.start_year + 1

    # Step 1: Resolve method names matching the query (case-insensitive substring).
    all_method_names = graph_repo.get_all_method_names() or []
    name_lower = req.method_name.lower()
    matched = [m for m in all_method_names if name_lower in m.lower()]

    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"No methods found matching: {req.method_name!r}",
        )

    try:
        trend_results = trend_svc.score(
            method_names=matched,
            year_end=req.end_year,
            recent_years=recent_years,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if not trend_results:
        raise HTTPException(
            status_code=404,
            detail=f"Methods matched {req.method_name!r} but no usage data found in "
                   f"{req.start_year}–{req.end_year}",
        )

    top = trend_results[0]  # highest-scored matching method

    # Step 2: Fetch paper IDs for the window, then extract the evolution path.
    paper_ids = graph_repo.get_paper_ids_by_year_range(
        req.start_year, req.end_year, limit=_BREAKTHROUGH_PAPER_LIMIT
    )

    evolution_steps: list[EvolutionStep] = []
    influence_scores: dict[str, float] = {}

    if paper_ids:
        try:
            breakthroughs = breakthrough_svc.detect(
                paper_ids=paper_ids,
                year_start=req.start_year,
                year_end=req.end_year,
                top_k=50,
            )
            evo_paths = evolution_svc.extract(
                method_names=matched,
                trend_scores=trend_results,
                breakthrough_candidates=breakthroughs,
                top_k=5,
            )
            if evo_paths:
                top_path = evo_paths[0]
                for i, (src, tgt) in enumerate(zip(top_path.path, top_path.path[1:])):
                    evolution_steps.append(
                        EvolutionStep(
                            from_method=src,
                            to_method=tgt,
                            relation_type=top_path.relation_types[i],
                        )
                    )
                influence_scores = dict(top_path.influence_scores)
        except Exception as exc:
            logger.error(
                "Evolution path extraction failed for method=%r: %s",
                req.method_name,
                exc,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="Evolution path extraction failed. Please try again later.",
            ) from exc

    logger.info(
        "Evolution trace method=%r window=%d–%d → %d path steps",
        req.method_name,
        req.start_year,
        req.end_year,
        len(evolution_steps),
    )
    return EvolutionResponse(
        method_name=top.method_name,
        evolution_path=evolution_steps,
        yearly_counts={str(year): count for year, count in sorted(top.yearly_counts.items())},
        influence_scores=influence_scores,
    )
