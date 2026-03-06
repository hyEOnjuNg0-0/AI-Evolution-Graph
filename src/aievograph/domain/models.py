from typing import ClassVar, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime


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
