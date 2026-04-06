from typing import ClassVar, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime



# Author
#  ├ author_id
#  └ name
class Author(BaseModel):
    model_config = ConfigDict(frozen=True)

    author_id: str
    name: str

    @field_validator("author_id", "name")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be empty.")
        return value


# Method
#  ├ name
#  ├ method_type
#  └ description
class Method(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    method_type: Literal["Method", "Model", "Technique", "Framework"]
    description: str | None = None

    @field_validator("name")
    @classmethod
    def method_name_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Method name must not be empty.")
        return value


# Paper
#  ├ paper_id
#  ├ title
#  ├ publication_year
#  ├ venue
#  ├ abstract
#  ├ citation_count
#  ├ reference_count
#  ├ referenced_work_ids
#  └ authors
class Paper(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_id: str
    title: str
    current_year: ClassVar[int] = datetime.now().year
    publication_year: int = Field(..., ge=1930, le=current_year)
    venue: str | None = None
    abstract: str | None = None
    citation_count: int = Field(default=0, ge=0)
    reference_count: int = Field(default=0, ge=0)
    referenced_work_ids: tuple[str, ...] = Field(default_factory=tuple)
    authors: list[Author] = Field(default_factory=list)

    @field_validator("paper_id", "title")
    @classmethod
    def paper_fields_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required string fields must not be empty.")
        return value

# MethodRelation
#  ├ source_method (name)
#  ├ target_method (name)
#  ├ relation_type
#  └ evidence
class MethodRelation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_method: str
    target_method: str
    relation_type: Literal["IMPROVES", "EXTENDS", "REPLACES"]
    evidence: str

    @field_validator("source_method", "target_method", "evidence")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be empty.")
        return value


# ExtractionResult
#  ├ methods
#  └ relations
class ExtractionResult(BaseModel):
    """Structured output from LLM-based method extraction (single paper)."""

    methods: list[Method] = Field(default_factory=list)
    relations: list[MethodRelation] = Field(default_factory=list)


# NormalizationMap
#  └ mapping  (variant name → canonical name)
class NormalizationMap(BaseModel):
    """Lookup table mapping variant method names to their canonical forms."""

    mapping: dict[str, str] = Field(default_factory=dict)

    def normalize(self, name: str) -> str:
        """Return canonical name, or the original if no mapping exists."""
        return self.mapping.get(name, name)


# Citation
#  ├ citing_paper_id
#  ├ cited_paper_id
#  └ created_year
class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    citing_paper_id: str
    cited_paper_id: str
    created_year: int = Field(..., ge=1900, le=2100)

    @field_validator("citing_paper_id", "cited_paper_id")
    @classmethod
    def citation_ids_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Citation IDs must not be empty.")
        return value


# ScoredPaper
#  ├ paper
#  ├ score
#  ├ semantic_sim  (optional — set by HybridRetrievalService)
#  └ graph_prox    (optional — set by HybridRetrievalService)
class ScoredPaper(BaseModel):
    """A Paper paired with a numeric ranking score.

    Used across multiple ranking layers (semantic similarity, centrality, etc.).
    The score semantics depend on the producing service; ge=0.0 is the only invariant.

    semantic_sim and graph_prox are optionally populated by HybridRetrievalService to
    expose the individual score components for Evidence Panel display in Layer E.
    """

    paper: "Paper"
    score: float = Field(..., ge=0.0)
    semantic_sim: float | None = None  # cosine similarity from vector search (0–1)
    graph_prox: float | None = None    # 1/hop_dist from graph expansion (0–1)


# Subgraph
#  └ papers  (ranked ScoredPaper list)
class Subgraph(BaseModel):
    """Query-specific subgraph produced by hybrid retrieval.

    papers is ordered by hybrid_score descending and capped at top_k.
    """

    papers: list["ScoredPaper"] = Field(default_factory=list)

    @model_validator(mode="after")
    def papers_must_have_unique_ids(self) -> "Subgraph":
        """Reject duplicate paper_ids so callers get a loud error instead of silent data loss."""
        seen: set[str] = set()
        for sp in self.papers:
            pid = sp.paper.paper_id
            if pid in seen:
                raise ValueError(f"Duplicate paper_id in Subgraph: {pid!r}")
            seen.add(pid)
        return self


# CentralityScores
#  ├ paper_id
#  ├ pagerank        (normalized to [0, 1])
#  ├ betweenness     (normalized to [0, 1])
#  └ combined_score  (γ×pagerank + (1−γ)×betweenness)
class CentralityScores(BaseModel):
    """Per-paper structural importance scores from GDS centrality algorithms."""

    paper_id: str
    pagerank: float = Field(default=0.0, ge=0.0)
    betweenness: float = Field(default=0.0, ge=0.0)
    combined_score: float = Field(default=0.0, ge=0.0)


# RankingResult
#  ├ top_papers      (combined-score 기준 상위 k개)
#  └ backbone_paths  (citation DAG에서 추출한 연구 계보 경로, 오래된 논문 → 최신 논문 순)
class RankingResult(BaseModel):
    """Output of Layer C combined ranking pipeline (Step 4.3).

    top_papers: Combined-score sorted list (centrality + semantic).
    backbone_paths: Each path is a list of paper_ids ordered oldest → newest,
                    forming a research lineage chain in the citation subgraph.
    """

    top_papers: list[ScoredPaper] = Field(default_factory=list)
    backbone_paths: list[list[str]] = Field(default_factory=list)


# BreakthroughCandidate
#  ├ paper_id
#  ├ burst_score         (Kleinberg citation burst intensity, normalized [0, 1])
#  ├ centrality_shift    (recent vs past citation rate gain, normalized [0, 1])
#  └ breakthrough_score  (α×burst + (1−α)×shift, normalized [0, 1])
class BreakthroughCandidate(BaseModel):
    """Per-paper breakthrough signal produced by Layer D Step 5.1.

    burst_score: Normalized Kleinberg burst intensity across the analysis window.
    centrality_shift: Normalized citation-rate gain from past half to recent half of window.
    breakthrough_score: Weighted combination of the two signals.
    """

    paper_id: str
    burst_score: float = Field(default=0.0, ge=0.0, le=1.0)
    centrality_shift: float = Field(default=0.0, ge=0.0, le=1.0)
    breakthrough_score: float = Field(default=0.0, ge=0.0, le=1.0)


# MethodTrendScore
#  ├ method_name
#  ├ cagr_score               (recent citation CAGR, normalized [0, 1])
#  ├ entropy_score            (Shannon entropy of adopting venues, normalized [0, 1])
#  ├ adoption_velocity_score  (linear trend slope of usage counts, normalized [0, 1])
#  └ trend_score              (α×CAGR + β×Entropy + γ×Velocity, normalized [0, 1])
class MethodTrendScore(BaseModel):
    """Per-method trend momentum signal produced by Layer D Step 5.2.

    cagr_score: Normalized compound annual growth rate of paper usage over recent window.
    entropy_score: Normalized Shannon entropy of citing-paper venue diversity.
    adoption_velocity_score: Normalized linear-regression slope of yearly usage counts.
    trend_score: Weighted combination of the three signals.
    """

    method_name: str
    cagr_score: float = Field(default=0.0, ge=0.0, le=1.0)
    entropy_score: float = Field(default=0.0, ge=0.0, le=1.0)
    adoption_velocity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    trend_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # Raw yearly paper-usage counts from the repository (year → count).
    # Used by callers that need the time series, e.g. to build yearly_scores in the API response.
    yearly_counts: dict[int, int] = Field(default_factory=dict)


# EvolutionPath
#  ├ path              (method names ordered oldest → newest)
#  ├ relation_types    (edge type for each step, len = len(path) - 1)
#  ├ branch_points     (methods on this path with out-degree ≥ 2)
#  ├ influence_scores  (method_name → combined influence score, normalized [0, 1])
#  └ mean_influence    (mean influence of all methods on this path)
class EvolutionPath(BaseModel):
    """A research-lineage path through the Method Evolution Graph (Layer D Step 5.3).

    path: Sequence of method names in research-flow order (oldest method first).
    relation_types: One relation type string per consecutive pair in path
                    (IMPROVES, EXTENDS, or REPLACES).
    branch_points: Subset of path methods where the evolution graph diverges
                   (out-degree >= 2 in the method subgraph).
    influence_scores: Per-method combined influence (trend + breakthrough proxy),
                      max-normalized to [0, 1] across all candidate methods.
    mean_influence: Mean of influence_scores for methods on this path; used for ranking.
    """

    path: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    branch_points: list[str] = Field(default_factory=list)
    influence_scores: dict[str, float] = Field(default_factory=dict)
    mean_influence: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check_relation_types_length(self) -> "EvolutionPath":
        expected = max(len(self.path) - 1, 0)
        if len(self.relation_types) != expected:
            raise ValueError(
                f"len(relation_types) must equal len(path) - 1 "
                f"(expected {expected}, got {len(self.relation_types)})"
            )
        return self
