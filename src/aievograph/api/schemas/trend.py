from pydantic import BaseModel, Field, model_validator


class TrendRequest(BaseModel):
    start_year: int = Field(..., ge=1930, le=2030, description="Analysis period start year")
    end_year: int = Field(..., ge=1930, le=2030, description="Analysis period end year")
    top_k: int = Field(30, ge=1, le=200, description="Number of top methods to return")

    @model_validator(mode="after")
    def validate_year_range(self) -> "TrendRequest":
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


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
