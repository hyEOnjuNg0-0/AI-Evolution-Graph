"""Shared file-system JSON cache and checkpoint utilities for infrastructure clients."""

import hashlib
import json
from pathlib import Path
from typing import Any


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
