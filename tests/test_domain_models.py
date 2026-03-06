import pytest
from pydantic import ValidationError

from aievograph.domain.models import Author, Citation, Method, Paper


def test_author_is_created_with_valid_data() -> None:
    author = Author(author_id="A-1", name="Alice")
    assert author.author_id == "A-1"
    assert author.name == "Alice"


def test_paper_requires_non_empty_title() -> None:
    with pytest.raises(ValidationError):
        Paper(
            paper_id="P-1",
            title="",
            publication_year=2024,
        )


def test_method_type_is_limited() -> None:
    with pytest.raises(ValidationError):
        Method(name="NewMethod", method_type="Algorithm")  # type: ignore[arg-type]


def test_citation_year_range_is_validated() -> None:
    with pytest.raises(ValidationError):
        Citation(citing_paper_id="P-1", cited_paper_id="P-2", created_year=1800)
