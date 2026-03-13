"""
Data ingestion script: Semantic Scholar → Neo4j

Usage:
  python scripts/ingest.py                      # settings from .env
  python scripts/ingest.py --venues NeurIPS ICML --year-start 2020 --year-end 2023
"""

import argparse
import asyncio
import logging
import sys

from neo4j import GraphDatabase

from aievograph.config.settings import TARGET_ARXIV_CATEGORIES, TARGET_VENUES, get_settings
from aievograph.domain.services.citation_graph_service import CitationGraphService
from aievograph.infrastructure.arxiv_client import ArxivClient
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository
from aievograph.infrastructure.semantic_scholar_client import SemanticScholarClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest papers into Neo4j.")
    parser.add_argument(
        "--venues",
        nargs="+",
        default=None,
        help="Venue names (default: all TARGET_VENUES from settings)",
    )
    parser.add_argument(
        "--year-start",
        type=int,
        default=None,
        help="Start year (default: COLLECT_YEAR_START from .env)",
    )
    parser.add_argument(
        "--year-end",
        type=int,
        default=None,
        help="End year (default: COLLECT_YEAR_END from .env)",
    )
    parser.add_argument(
        "--arxiv",
        action="store_true",
        default=False,
        help="Also collect arXiv preprints via arXiv API + Semantic Scholar enrichment",
    )
    parser.add_argument(
        "--arxiv-categories",
        nargs="+",
        default=None,
        help="arXiv categories to collect (default: TARGET_ARXIV_CATEGORIES from settings)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()

    venues = args.venues or TARGET_VENUES
    year_start = args.year_start or settings.collect_year_start
    year_end = args.year_end or settings.collect_year_end

    logger.info(
        "Ingestion start — venues=%d, years=%d-%d", len(venues), year_start, year_end
    )

    # 1. Collect papers from Semantic Scholar
    collector = SemanticScholarClient(settings)
    papers = await collector.collect(venues, year_start, year_end)
    logger.info("Collected %d conference papers.", len(papers))

    # 1b. Optionally collect arXiv preprints via arXiv API + S2 enrichment
    if args.arxiv:
        categories = args.arxiv_categories or TARGET_ARXIV_CATEGORIES
        logger.info("Collecting arXiv papers — categories=%s", categories)
        arxiv_collector = ArxivClient(settings)
        arxiv_papers = await arxiv_collector.collect(categories, year_start, year_end)
        logger.info("Collected %d arXiv papers.", len(arxiv_papers))
        # Merge: deduplicate by paper_id (conference copy takes precedence)
        existing_ids = {p.paper_id for p in papers}
        papers = papers + [p for p in arxiv_papers if p.paper_id not in existing_ids]
        logger.info("Total after merge: %d papers.", len(papers))

    if not papers:
        logger.warning("No papers collected. Check venues/year range or API key.")
        return

    # 2. Store in Neo4j
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        repo = Neo4jGraphRepository(driver)
        service = CitationGraphService(repo)
        service.build_citation_graph(papers)
        logger.info("Ingestion complete.")
    finally:
        driver.close()


if __name__ == "__main__":
    asyncio.run(main())
