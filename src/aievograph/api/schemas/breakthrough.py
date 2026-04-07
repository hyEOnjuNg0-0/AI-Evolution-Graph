from pydantic import BaseModel, Field, field_validator, model_validator


class BreakthroughRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=500, description="Research field or keyword to analyze")
    start_year: int = Field(..., ge=1930, le=2030, description="Time window start year")
    end_year: int = Field(..., ge=1930, le=2030, description="Time window end year")
    top_k: int = Field(10, ge=1, le=50, description="Max breakthrough candidates to return")

    @field_validator("field", mode="before")
    @classmethod
    def field_not_blank(cls, v: str) -> str:
        if isinstance(v, str) and not v.strip():
            raise ValueError("field must not be blank")
        return v

    @model_validator(mode="after")
    def validate_year_range(self) -> "BreakthroughRequest":
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


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
