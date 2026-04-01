from typing import Literal

from pydantic import BaseModel, Field, model_validator

QueryType = Literal["semantic", "structural", "balanced"]


class LineageRequest(BaseModel):
    seed: str = Field(..., description="Natural-language keyword or paper title to search")
    hop_depth: int = Field(2, ge=1, le=5, description="Citation graph traversal depth")
    start_year: int | None = Field(None, description="Filter: papers published from this year")
    end_year: int | None = Field(None, description="Filter: papers published up to this year")
    top_k: int = Field(20, ge=1, le=100, description="Max papers to return")
    query_type: QueryType = Field("balanced", description="semantic (α=0.9/β=0.1) · structural (α=0.1/β=0.9) · balanced (α=0.5/β=0.5)")

    @model_validator(mode="after")
    def validate_year_range(self) -> "LineageRequest":
        if self.start_year is not None and self.end_year is not None:
            if self.start_year > self.end_year:
                raise ValueError("start_year must be <= end_year")
        return self


class PaperNode(BaseModel):
    paper_id: str
    title: str
    year: int | None
    authors: list[str]
    citation_count: int
    score: float | None = None


class CitationEdge(BaseModel):
    source_id: str
    target_id: str


class LineageResponse(BaseModel):
    papers: list[PaperNode]
    edges: list[CitationEdge]
    total: int
