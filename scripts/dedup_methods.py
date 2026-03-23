"""
Deduplicate Method nodes in Neo4j.

Usage:
  python scripts/dedup_methods.py                       # merge duplicate Method nodes
  python scripts/dedup_methods.py --dry-run             # preview merges without touching DB
  python scripts/dedup_methods.py --llm-model gpt-4o   # use a different OpenAI model
"""

import argparse
import logging
import sys

from neo4j import GraphDatabase
from openai import OpenAI

from aievograph.config.settings import get_settings
from aievograph.domain.models import NormalizationMap
from aievograph.domain.services.method_deduplication_service import MethodDeduplicationService
from aievograph.infrastructure.llm_entity_normalizer import LLMEntityNormalizer
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate Method nodes in Neo4j.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the normalization map without modifying the database.",
    )
    parser.add_argument(
        "--llm-model",
        default="gpt-4o-mini",
        help="OpenAI model used by the normalizer (default: gpt-4o-mini).",
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


def main() -> None:
    args = parse_args()
    settings = get_settings()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        repo = Neo4jGraphRepository(driver)
        openai_client = OpenAI(api_key=settings.openai_api_key)
        normalizer = LLMEntityNormalizer(openai_client, model=args.llm_model)
        service = MethodDeduplicationService(repo, normalizer)

        if args.dry_run:
            norm_map = service.plan()
            _log_merges(norm_map, prefix="Dry-run: ")
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
