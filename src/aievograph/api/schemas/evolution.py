from pydantic import BaseModel, Field, field_validator

from aievograph.api.schemas.common import YearRangeRequest, validate_not_blank


class EvolutionRequest(YearRangeRequest):
    method_name: str = Field(..., min_length=1, max_length=500, description="Method name to trace evolution path")
    start_year: int = Field(..., ge=1930, le=2030, description="Analysis period start year")
    end_year: int = Field(..., ge=1930, le=2030, description="Analysis period end year")

    @field_validator("method_name", mode="before")
    @classmethod
    def method_name_not_blank(cls, v: str) -> str:
        return validate_not_blank("method_name", v)


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
