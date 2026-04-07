from pydantic import BaseModel, Field

from aievograph.api.schemas.common import YearRangeRequest


class TrendRequest(YearRangeRequest):
    start_year: int = Field(..., ge=1930, le=2030, description="Analysis period start year")
    end_year: int = Field(..., ge=1930, le=2030, description="Analysis period end year")
    top_k: int = Field(30, ge=1, le=200, description="Number of top methods to return")


class TrendMethodResult(BaseModel):
    method_name: str
    cagr: float
    entropy: float
    adoption_velocity: float
    momentum_score: float
    yearly_counts: dict[str, int]   # JSON keys are strings (year as str)


class TrendResponse(BaseModel):
    start_year: int
    end_year: int
    methods: list[TrendMethodResult]
