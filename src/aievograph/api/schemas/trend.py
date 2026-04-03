from pydantic import BaseModel, Field, model_validator


class TrendRequest(BaseModel):
    topic: str = Field(..., description="Method or topic name to analyze")
    start_year: int = Field(..., description="Analysis period start year")
    end_year: int = Field(..., description="Analysis period end year")

    @model_validator(mode="after")
    def validate_year_range(self) -> "TrendRequest":
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


class YearlyScore(BaseModel):
    year: int
    usage_count: int
    score: float


class EvolutionStep(BaseModel):
    from_method: str
    to_method: str
    relation_type: str
    year: int | None


class MethodScore(BaseModel):
    method: str
    score: float


class TrendResponse(BaseModel):
    topic: str
    cagr: float
    entropy: float
    adoption_velocity: float
    momentum_score: float
    yearly_scores: list[YearlyScore]
    evolution_path: list[EvolutionStep]
    method_scores: list[MethodScore]
    evolution_error: str | None = None
