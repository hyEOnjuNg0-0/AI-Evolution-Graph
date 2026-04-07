from typing import Literal

from pydantic import BaseModel, Field, field_validator

from aievograph.api.schemas.common import YearRangeRequest, validate_not_blank

QueryType = Literal["semantic", "structural", "balanced"]


class LineageRequest(YearRangeRequest):
    seed: str = Field(..., min_length=1, max_length=500, description="Natural-language keyword or paper title to search")
    hop_depth: int = Field(2, ge=1, le=5, description="Citation graph traversal depth")
    start_year: int | None = Field(None, description="Filter: papers published from this year")
    end_year: int | None = Field(None, description="Filter: papers published up to this year")
    top_k: int = Field(20, ge=1, le=100, description="Max papers to return")
    query_type: QueryType = Field("balanced", description="semantic (α=0.9/β=0.1) · structural (α=0.1/β=0.9) · balanced (α=0.5/β=0.5)")

    @field_validator("seed", mode="before")
    @classmethod
    def seed_not_blank(cls, v: str) -> str:
        return validate_not_blank("seed", v)


class PaperNode(BaseModel):
    paper_id: str
    title: str
    year: int | None
    authors: list[str]
    citation_count: int
    score: float | None = None
    semantic_similarity: float | None = None  # cosine similarity component of hybrid score
    graph_proximity: float | None = None      # graph distance component of hybrid score


class CitationEdge(BaseModel):
    source_id: str
    target_id: str


class LineageResponse(BaseModel):
    papers: list[PaperNode]
    edges: list[CitationEdge]
    total: int
