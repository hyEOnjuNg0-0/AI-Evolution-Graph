from pydantic import BaseModel, Field


class LineageRequest(BaseModel):
    seed: str = Field(..., description="Seed paper ID (S2 paper ID) or keyword")
    hop_depth: int = Field(2, ge=1, le=5, description="Citation graph traversal depth")
    start_year: int | None = Field(None, description="Filter: papers published from this year")
    end_year: int | None = Field(None, description="Filter: papers published up to this year")
    top_k: int = Field(20, ge=1, le=100, description="Max papers to return")


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
