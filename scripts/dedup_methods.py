"""
Deduplicate Method nodes in Neo4j.

Usage:
  python scripts/dedup_methods.py                            # merge duplicate Method nodes
  python scripts/dedup_methods.py --dry-run                  # preview merges without touching DB
  python scripts/dedup_methods.py --dry-run --save-plan p.json   # preview + save plan to file
  python scripts/dedup_methods.py --apply-plan p.json        # apply saved plan (no LLM call)
  python scripts/dedup_methods.py --llm-model gpt-4o         # use a different OpenAI model
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from neo4j import GraphDatabase
from openai import OpenAI

from aievograph.config.settings import get_settings
from aievograph.infrastructure.logging import configure_logging
from aievograph.domain.models import NormalizationMap
from aievograph.domain.services.method_deduplication_service import MethodDeduplicationService
from aievograph.infrastructure.llm_entity_normalizer import LLMEntityNormalizer
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

configure_logging()
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate Method nodes in Neo4j.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the normalization map without modifying the database.",
    )
    mode.add_argument(
        "--apply-plan",
        metavar="FILE",
        help="Apply a saved plan file to the database without calling the LLM.",
    )
    parser.add_argument(
        "--save-plan",
        metavar="FILE",
        help="Save the dry-run plan to a JSON file (use with --dry-run).",
    )
    parser.add_argument(
        "--llm-model",
        default="gpt-4o",
        help="OpenAI model used by the normalizer (default: gpt-4o).",
    )
    return parser.parse_args()


def _log_merges(norm_map: NormalizationMap, prefix: str) -> None:
    merges = {v: c for v, c in norm_map.mapping.items() if v != c}
    if merges:
        logger.info("%s%d merges:", prefix, len(merges))
        for variant, canonical in sorted(merges.items()):
            logger.info("  '%s'  →  '%s'", variant, canonical)
    else:
        logger.info("%sno duplicates detected.", prefix)


def _load_plan(path: str) -> NormalizationMap:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return NormalizationMap(mapping=data)


def _save_plan(norm_map: NormalizationMap, path: str) -> None:
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(norm_map.mapping, ensure_ascii=False), encoding="utf-8")
    tmp.replace(Path(path))
    logger.info("Plan saved to '%s'.", path)


def main() -> None:
    args = parse_args()
    settings = get_settings()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        repo = Neo4jGraphRepository(driver)

        if args.apply_plan:
            # Load pre-computed plan and apply without LLM
            norm_map = _load_plan(args.apply_plan)
            logger.info("Loaded plan from '%s' (%d entries).", args.apply_plan, len(norm_map.mapping))
            # normalizer is not needed for apply — pass None-safe stub via service
            service = MethodDeduplicationService(repo, normalizer=None)  # type: ignore[arg-type]
            norm_map = service.apply(norm_map)
            _log_merges(norm_map, prefix="Deduplication complete — ")
        else:
            openai_client = OpenAI(api_key=settings.openai_api_key)
            normalizer = LLMEntityNormalizer(openai_client, model=args.llm_model)
            service = MethodDeduplicationService(repo, normalizer)

            if args.dry_run:
                norm_map = service.plan()
                _log_merges(norm_map, prefix="Dry-run: ")
                if args.save_plan:
                    _save_plan(norm_map, args.save_plan)
            else:
                norm_map = service.deduplicate()
                _log_merges(norm_map, prefix="Deduplication complete — ")

    except Exception:
        logger.exception("Deduplication failed.")
        sys.exit(1)
    finally:
        driver.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
