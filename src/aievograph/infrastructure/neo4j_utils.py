"""Shared Neo4j query utilities for infrastructure repositories."""

from typing import Any, Callable, TypeVar

from neo4j import Driver

from aievograph.domain.models import Author, Paper

T = TypeVar("T")


def record_to_paper(record: Any) -> Paper:
    """Convert a Neo4j record to a Paper domain object.

    Uses .get() for all node fields so that missing properties raise a
    descriptive ValueError instead of a bare KeyError.
    Expects the record to have a 'p' node and an 'authors' list field.
    """
    node = record["p"]
    paper_id = node.get("paper_id")
    title = node.get("title")
    publication_year = node.get("publication_year")
    if paper_id is None or title is None or publication_year is None:
        raise ValueError(
            f"Paper node missing required fields: "
            f"paper_id={paper_id!r}, title={title!r}, publication_year={publication_year!r}"
        )
    raw_authors: list[Any] = record["authors"] or []
    authors = [
        Author(author_id=a["author_id"], name=a["name"])
        for a in raw_authors
        if a is not None and a.get("author_id") and a.get("name")
    ]
    return Paper(
        paper_id=paper_id,
        title=title,
        publication_year=publication_year,
        venue=node.get("venue"),
        abstract=node.get("abstract"),
        citation_count=node.get("citation_count") or 0,
        reference_count=node.get("reference_count") or 0,
        authors=authors,
    )


def run_grouped_query(
    driver: Driver,
    cypher: str,
    params: dict[str, Any],
    group_key: str,
    sub_key: str,
    value_key: str = "cnt",
    *,
    sub_key_cast: Callable | None = None,
    value_cast: Callable = int,
) -> dict:
    """Execute a Cypher query and accumulate results into a nested dict.

    Args:
        driver: Neo4j driver instance.
        cypher: Cypher query string.
        params: Query parameters passed as keyword arguments to session.run().
        group_key: Record field name for the outer dict key.
        sub_key: Record field name for the inner dict key.
        value_key: Record field name for the leaf value (default "cnt").
        sub_key_cast: Optional callable to cast the sub_key value (e.g. int for year fields).
        value_cast: Callable to cast the leaf value (default int).

    Returns:
        Nested dict {group_value: {sub_value: cast_value}}.
    """
    result: dict = {}
    with driver.session() as session:
        for r in session.run(cypher, **params):
            group = r[group_key]
            sub = sub_key_cast(r[sub_key]) if sub_key_cast else r[sub_key]
            val = value_cast(r[value_key])
            result.setdefault(group, {})[sub] = val
    return result


def run_and_collect(
    driver: Driver,
    cypher: str,
    params: dict[str, Any],
    row_fn: Callable[[Any], T],
    *,
    filter_none: bool = False,
) -> list[T]:
    """Execute a Cypher query and map each record to a value via row_fn.

    Args:
        driver: Neo4j driver instance.
        cypher: Cypher query string.
        params: Query parameters passed as keyword arguments to session.run().
        row_fn: Callable that maps a Neo4j Record to the desired output value.
        filter_none: When True, rows for which row_fn returns None are excluded.

    Returns:
        List of mapped values, optionally filtered of None results.
    """
    results: list[T] = []
    with driver.session() as session:
        for r in session.run(cypher, **params):
            value = row_fn(r)
            if filter_none and value is None:
                continue
            results.append(value)
    return results


def run_and_group_list(
    driver: Driver,
    cypher: str,
    params: dict[str, Any],
    group_key: str,
    value_key: str,
) -> dict[str, list]:
    """Execute a Cypher query and accumulate results into a dict of lists.

    Each record contributes one value to the list keyed by group_key.
    This is the canonical pattern for building paper→methods or similar
    one-to-many mappings without manual setdefault/append boilerplate.

    Args:
        driver: Neo4j driver instance.
        cypher: Cypher query string.
        params: Query parameters passed as keyword arguments to session.run().
        group_key: Record field name used as the outer dict key.
        value_key: Record field name whose value is appended to the inner list.

    Returns:
        Dict mapping each unique group_key value to a list of value_key values.
    """
    result: dict[str, list] = {}
    with driver.session() as session:
        for r in session.run(cypher, **params):
            key = r[group_key]
            result.setdefault(key, []).append(r[value_key])
    return result
