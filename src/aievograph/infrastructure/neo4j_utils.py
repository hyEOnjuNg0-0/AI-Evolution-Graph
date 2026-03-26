"""Shared Neo4j query utilities for infrastructure repositories."""

from typing import Any, Callable

from neo4j import Driver


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
