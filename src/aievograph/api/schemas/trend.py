from pydantic import BaseModel, Field


class TrendRequest(BaseModel):
    topic: str = Field(..., description="Method or topic name to analyze")
    start_year: int = Field(..., description="Analysis period start year")
    end_year: int = Field(..., description="Analysis period end year")


class YearlyScore(BaseModel):
    year: int
    usage_count: int
    score: float


class EvolutionStep(BaseModel):
    from_method: str
    to_method: str
    relation_type: str
    year: int | None


class TrendResponse(BaseModel):
    topic: str
    cagr: float
    entropy: float
    adoption_velocity: float
    momentum_score: float
    yearly_scores: list[YearlyScore]
    evolution_path: list[EvolutionStep]
