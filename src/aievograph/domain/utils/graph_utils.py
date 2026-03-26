"""Shared DAG path extraction utilities for Layer C and Layer D services."""


def extract_dag_paths(
    node_ids: set[str],
    edges: list[tuple[str, str]],
    scores: dict[str, float],
    *,
    min_path_length: int = 2,
    top_k: int | None = None,
) -> list[list[str]]:
    """Extract all maximal paths from a DAG using exhaustive DFS.

    Traverses from source nodes (no predecessors) using greedy successor ordering
    (highest-score neighbors first). Collects every leaf-terminated path of
    length >= min_path_length, then sorts by mean score descending.

    Args:
        node_ids: Set of node IDs that form the subgraph.
        edges: (src, tgt) pairs representing directed edges src -> tgt.
            Self-loops and edges outside node_ids are discarded.
        scores: Score per node_id used for DFS ordering and path ranking.
        min_path_length: Minimum number of nodes a path must have to be included.
        top_k: If provided, return only the top_k paths by mean score.

    Returns:
        List of node_id paths sorted by mean score descending.
        Path itself is used as a deterministic tiebreaker for equal-score paths.
    """
    successors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    predecessors: dict[str, set[str]] = {nid: set() for nid in node_ids}

    for src, tgt in edges:
        if src in node_ids and tgt in node_ids and src != tgt:
            successors[src].append(tgt)
            predecessors[tgt].add(src)

    # Sort successors by score descending for greedy DFS ordering.
    for nid in successors:
        successors[nid].sort(key=lambda x: -scores.get(x, 0.0))

    sources = sorted(nid for nid in node_ids if not predecessors[nid])

    paths: list[list[str]] = []

    def _dfs(node: str, path: list[str], visited: set[str]) -> None:
        next_nodes = [s for s in successors[node] if s not in visited]
        if not next_nodes:
            if len(path) >= min_path_length:
                paths.append(list(path))
            return
        for nxt in next_nodes:
            path.append(nxt)
            visited.add(nxt)
            _dfs(nxt, path, visited)
            path.pop()
            visited.discard(nxt)

    for src in sources:
        _dfs(src, [src], {src})

    paths.sort(
        key=lambda p: (-(sum(scores.get(nid, 0.0) for nid in p) / len(p)), p)
    )

    return paths[:top_k] if top_k is not None else paths
