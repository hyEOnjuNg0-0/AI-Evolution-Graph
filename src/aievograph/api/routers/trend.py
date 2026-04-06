"""
Trending Methods Discovery endpoint (Feature ③ — Discovery mode).

POST /api/trend
  - Returns TOP-K methods ranked by momentum score (CAGR + entropy + adoption velocity)
    within the requested year range, without requiring a topic filter.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from aievograph.api.dependencies import get_trend_service
from aievograph.api.schemas.trend import TrendMethodResult, TrendRequest, TrendResponse
from aievograph.domain.services.trend_momentum_service import TrendMomentumService

router = APIRouter(prefix="/api/trend", tags=["trend"])
logger = logging.getLogger(__name__)


@router.post("", response_model=TrendResponse)
def discover_trending(
    req: TrendRequest,
    trend_svc: TrendMomentumService = Depends(get_trend_service),
) -> TrendResponse:
    """Discover trending methods within a year range.

    Scores ALL known methods by CAGR, Shannon entropy, and adoption velocity,
    then returns the top_k ranked by composite momentum score.
    """
    recent_years = req.end_year - req.start_year + 1

    try:
        # Discovery mode: method_names=None triggers full-scan queries
        trend_results = trend_svc.score(
            method_names=None,
            year_end=req.end_year,
            recent_years=recent_years,
            top_k=req.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    logger.info(
        "Trend discovery window=%d–%d top_k=%d → %d methods returned",
        req.start_year,
        req.end_year,
        req.top_k,
        len(trend_results),
    )
    return TrendResponse(
        start_year=req.start_year,
        end_year=req.end_year,
        methods=[
            TrendMethodResult(
                method_name=m.method_name,
                cagr=m.cagr_score,
                entropy=m.entropy_score,
                adoption_velocity=m.adoption_velocity_score,
                momentum_score=m.trend_score,
                yearly_counts={str(year): count for year, count in sorted(m.yearly_counts.items())},
            )
            for m in trend_results
        ],
    )
