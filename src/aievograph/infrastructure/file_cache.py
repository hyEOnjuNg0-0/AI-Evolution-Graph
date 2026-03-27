"""Shared file-system JSON cache and checkpoint utilities for infrastructure clients."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def build_cache_key(*parts: str) -> str:
    """Return a SHA-256 hex digest built from colon-joined parts.

    Provides a deterministic, filesystem-safe cache key for any number of
    string components (e.g. category, year range, pagination token).
    """
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def chunk_items(items: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive non-overlapping sublists of `size` from `items`.

    The last chunk may be shorter than `size` when len(items) is not a
    multiple of `size`.
    """
    for i in range(0, len(items), size):
        yield items[i : i + size]


def read_json(cache_dir: Path, key: str) -> Any | None:
    """Return parsed JSON from cache_dir/<key>.json, or None if absent."""
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def write_json(cache_dir: Path, key: str, data: Any) -> None:
    """Write data as JSON to cache_dir/<key>.json."""
    (cache_dir / f"{key}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def checkpoint_path(cache_dir: Path, keys: list[str], year_range: str) -> Path:
    """Return the Path for a checkpoint file derived from sorted keys and year_range."""
    digest = hashlib.sha256(
        f"{','.join(sorted(keys))}:{year_range}".encode()
    ).hexdigest()[:16]
    return cache_dir / f"checkpoint_{digest}.json"


def load_checkpoint(path: Path) -> dict[str, Any]:
    """Return checkpoint data from path, or an empty dict if the file does not exist."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_checkpoint(path: Path, data: dict[str, Any]) -> None:
    """Persist checkpoint data to path as JSON."""
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
