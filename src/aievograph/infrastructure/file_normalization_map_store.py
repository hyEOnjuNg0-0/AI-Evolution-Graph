"""File-backed NormalizationMapStore: persists mapping as JSON on disk."""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from aievograph.domain.models import NormalizationMap
from aievograph.domain.ports.normalization_map_store import NormalizationMapStorePort

logger = logging.getLogger(__name__)

_FILENAME = "normalization_map.json"


class FileNormalizationMapStore(NormalizationMapStorePort):
    """Stores NormalizationMap.mapping as JSON at <store_dir>/normalization_map.json.

    load() is fault-tolerant: a corrupt or structurally invalid file is treated as
    absent (logs a warning, returns empty map) rather than crashing the ingest pipeline.

    save() writes atomically via a sibling .tmp file and an OS-level rename, so a
    mid-write crash cannot leave a half-written file behind.
    """

    def __init__(self, store_dir: Path) -> None:
        self._path = store_dir / _FILENAME
        store_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> NormalizationMap:
        if not self._path.exists():
            logger.debug("No persisted NormalizationMap found; returning empty map.")
            return NormalizationMap()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            norm_map = NormalizationMap(mapping=data)
            logger.debug("Loaded NormalizationMap with %d entries.", len(norm_map.mapping))
            return norm_map
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            logger.warning(
                "NormalizationMap file '%s' is corrupt (%s); starting with empty map.",
                self._path,
                exc,
            )
            return NormalizationMap()

    def save(self, norm_map: NormalizationMap) -> None:
        # Write to a sibling .tmp file first, then atomically replace the real file.
        # Path.replace() is atomic on POSIX and close-to-atomic on Windows (same volume).
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(norm_map.mapping, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self._path)
        logger.debug("Saved NormalizationMap with %d entries.", len(norm_map.mapping))
