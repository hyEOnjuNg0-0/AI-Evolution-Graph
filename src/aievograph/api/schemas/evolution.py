from pydantic import BaseModel, Field, model_validator


class EvolutionRequest(BaseModel):
    method_name: str = Field(..., description="Method name to trace evolution path")
    start_year: int = Field(..., ge=1930, le=2030, description="Analysis period start year")
    end_year: int = Field(..., ge=1930, le=2030, description="Analysis period end year")

    @model_validator(mode="after")
    def validate_year_range(self) -> "EvolutionRequest":
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


class EvolutionStep(BaseModel):
    from_method: str
    to_method: str
    relation_type: str
    year: int | None = None


class EvolutionResponse(BaseModel):
    method_name: str
    evolution_path: list[EvolutionStep]
    yearly_counts: dict[str, int]       # JSON keys are strings (year as str)
    influence_scores: dict[str, float]
