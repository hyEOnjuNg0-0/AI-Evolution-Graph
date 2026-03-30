from pydantic import BaseModel, Field


class BreakthroughRequest(BaseModel):
    field: str = Field(..., description="Research field or keyword to analyze")
    start_year: int = Field(..., description="Time window start year")
    end_year: int = Field(..., description="Time window end year")
    top_k: int = Field(10, ge=1, le=50, description="Max breakthrough candidates to return")


class BreakthroughCandidate(BaseModel):
    paper_id: str
    title: str
    year: int | None
    burst_score: float
    centrality_shift: float
    composite_score: float


class BreakthroughResponse(BaseModel):
    candidates: list[BreakthroughCandidate]
    total: int
