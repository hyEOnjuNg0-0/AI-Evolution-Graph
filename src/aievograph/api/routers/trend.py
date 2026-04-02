"""
Trend Momentum Analysis endpoint (Feature ③).

POST /api/trend
  - Scores a method/topic by CAGR, Shannon entropy, and adoption velocity.
  - Returns yearly usage counts and evolution paths through the Method Evolution Graph.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from aievograph.api.dependencies import (
    get_breakthrough_service,
    get_evolution_path_service,
    get_graph_repository,
    get_trend_service,
)
from aievograph.api.schemas.trend import EvolutionStep, MethodScore, TrendRequest, TrendResponse, YearlyScore
from aievograph.domain.services.breakthrough_detection_service import BreakthroughDetectionService
from aievograph.domain.services.evolution_path_service import EvolutionPathService
from aievograph.domain.services.trend_momentum_service import TrendMomentumService
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

router = APIRouter(prefix="/api/trend", tags=["trend"])
logger = logging.getLogger(__name__)


@router.post("", response_model=TrendResponse)
def analyze_trend(
    req: TrendRequest,
    graph_repo: Neo4jGraphRepository = Depends(get_graph_repository),
    trend_svc: TrendMomentumService = Depends(get_trend_service),
    breakthrough_svc: BreakthroughDetectionService = Depends(get_breakthrough_service),
    evolution_svc: EvolutionPathService = Depends(get_evolution_path_service),
) -> TrendResponse:
    """Compute trend momentum for a method/topic and return its evolution path.

    Pipeline:
      1. Fuzzy-match the topic against known method names.
      2. TrendMomentumService scores CAGR, entropy, and adoption velocity.
      3. EvolutionPathService extracts the research-lineage path.
    """
    recent_years = req.end_year - req.start_year + 1

    # Step 1: Resolve method names matching the topic (case-insensitive substring).
    all_method_names = graph_repo.get_all_method_names()
    topic_lower = req.topic.lower()
    matched = [m for m in all_method_names if topic_lower in m.lower()]

    # Fall back to the raw topic if no stored methods match (service will return score=0).
    method_names = matched if matched else [req.topic]

    try:
        trend_results = trend_svc.score(
            method_names=method_names,
            year_end=req.end_year,
            recent_years=recent_years,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if not trend_results:
        raise HTTPException(status_code=404, detail=f"No trend data found for topic: {req.topic!r}")

    top = trend_results[0]  # highest-scored matching method

    # Build yearly usage scores from the normalized trend scores per year.
    # MethodTrendScore does not carry raw yearly counts, so we synthesise
    # a single summary row from the aggregate scores.
    yearly_scores = [
        YearlyScore(year=req.end_year, usage_count=0, score=top.trend_score)
    ]

    # Step 3: Evolution path (requires trend + breakthrough signals).
    papers_in_window = graph_repo.get_papers_by_year_range(req.start_year, req.end_year)
    paper_ids = [p.paper_id for p in papers_in_window]

    evolution_steps: list[EvolutionStep] = []
    method_scores: list[MethodScore] = []
    if paper_ids:
        try:
            breakthroughs = breakthrough_svc.detect(
                paper_ids=paper_ids,
                year_start=req.start_year,
                year_end=req.end_year,
                top_k=50,
            )
            evo_paths = evolution_svc.extract(
                method_names=method_names,
                trend_scores=trend_results,
                breakthrough_candidates=breakthroughs,
                top_k=5,
            )
            # Flatten the top evolution path into steps and extract per-method influence scores.
            if evo_paths:
                top_path = evo_paths[0]
                for i, (src, tgt) in enumerate(zip(top_path.path, top_path.path[1:])):
                    evolution_steps.append(
                        EvolutionStep(
                            from_method=src,
                            to_method=tgt,
                            relation_type=top_path.relation_types[i],
                            year=None,
                        )
                    )
                method_scores = [
                    MethodScore(method=m, score=s)
                    for m, s in top_path.influence_scores.items()
                ]
        except Exception:
            logger.warning("Evolution path extraction failed for topic=%r", req.topic, exc_info=True)

    logger.info(
        "Trend analysis topic=%r window=%d–%d → score=%.3f",
        req.topic,
        req.start_year,
        req.end_year,
        top.trend_score,
    )
    return TrendResponse(
        topic=top.method_name,
        cagr=top.cagr_score,
        entropy=top.entropy_score,
        adoption_velocity=top.adoption_velocity_score,
        momentum_score=top.trend_score,
        yearly_scores=yearly_scores,
        evolution_path=evolution_steps,
        method_scores=method_scores,
    )
