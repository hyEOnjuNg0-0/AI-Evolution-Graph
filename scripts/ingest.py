"""
Data ingestion script: Semantic Scholar → Neo4j

Usage:
  python scripts/ingest.py                      # settings from .env
  python scripts/ingest.py --venues NeurIPS ICML --year-start 2020 --year-end 2023
  python scripts/ingest.py --method-graph            # also extract methods and store Method graph
  python scripts/ingest.py --method-graph-only       # skip paper collection, use papers already in Neo4j
  python scripts/ingest.py --method-graph --llm-model gpt-4o-mini  # cheaper model
"""

import argparse
import asyncio
import logging
import sys

from neo4j import GraphDatabase
from openai import OpenAI

from aievograph.config.settings import TARGET_ARXIV_CATEGORIES, TARGET_VENUES, get_settings
from aievograph.domain.services.citation_graph_service import CitationGraphService
from aievograph.domain.services.entity_normalization_service import EntityNormalizationService
from aievograph.domain.services.method_extraction_service import MethodExtractionService
from aievograph.domain.services.method_graph_service import MethodGraphService
from aievograph.infrastructure.arxiv_client import ArxivClient
from aievograph.infrastructure.llm_entity_normalizer import LLMEntityNormalizer
from aievograph.infrastructure.llm_method_extractor import LLMMethodExtractor
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
        "--arxiv-only",
        action="store_true",
        default=False,
        help="Collect arXiv preprints only, skip Semantic Scholar venue collection",
    )
    parser.add_argument(
        "--arxiv-categories",
        nargs="+",
        default=None,
        help="arXiv categories to collect (default: TARGET_ARXIV_CATEGORIES from settings)",
    )
    parser.add_argument(
        "--method-graph",
        action="store_true",
        default=False,
        help="Extract Method entities and relations from abstracts and store in Neo4j",
    )
    parser.add_argument(
        "--method-graph-only",
        action="store_true",
        default=False,
        help=(
            "Skip paper collection; load papers already in Neo4j and build Method graph only. "
            "Uses --year-start / --year-end to filter which papers to process."
        ),
    )
    parser.add_argument(
        "--llm-model",
        default="gpt-4o-mini",
        help="OpenAI model for method extraction and normalization (default: gpt-4o)",
    )
    return parser.parse_args()


def _build_method_graph(repo: Neo4jGraphRepository, papers: list, llm_model: str, settings) -> None:
    """Wire up and run the Method Evolution Graph pipeline."""
    logger.info("Starting Method Evolution Graph extraction (model=%s, papers=%d).", llm_model, len(papers))
    openai_client = OpenAI(api_key=settings.openai_api_key)
    extractor = LLMMethodExtractor(openai_client, model=llm_model)
    normalizer = LLMEntityNormalizer(openai_client, model=llm_model)
    method_service = MethodGraphService(
        repo,
        MethodExtractionService(extractor),
        EntityNormalizationService(normalizer),
    )
    norm_map = method_service.build_method_graph(papers)
    logger.info("Method graph complete. Normalization map: %d entries.", len(norm_map.mapping))


async def main() -> None:
    args = parse_args()
    settings = get_settings()

    year_start = args.year_start or settings.collect_year_start
    year_end = args.year_end or settings.collect_year_end

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        repo = Neo4jGraphRepository(driver)

        # --- Method-graph-only: skip collection, read papers from Neo4j ---
        if args.method_graph_only:
            logger.info(
                "Method-graph-only mode — loading papers from Neo4j (years=%d-%d).",
                year_start, year_end,
            )
            papers = repo.get_papers_by_year_range(year_start, year_end, venues=args.venues)
            logger.info("Loaded %d papers from Neo4j.", len(papers))
            if not papers:
                logger.warning(
                    "No papers found in Neo4j for years %d-%d. "
                    "Run without --method-graph-only first to collect and store papers.",
                    year_start, year_end,
                )
                return
            _build_method_graph(repo, papers, args.llm_model, settings)
            return

        # --- Normal mode: collect papers then store ---
        venues = args.venues or TARGET_VENUES
        logger.info("Ingestion start — venues=%d, years=%d-%d", len(venues), year_start, year_end)

        # 1a. Collect from Semantic Scholar (skip if --arxiv-only)
        if args.arxiv_only:
            papers = []
        else:
            collector = SemanticScholarClient(settings)
            papers = await collector.collect(venues, year_start, year_end)
            logger.info("Collected %d conference papers.", len(papers))

        # 1b. Collect arXiv preprints when --arxiv or --arxiv-only is set
        if args.arxiv or args.arxiv_only:
            categories = args.arxiv_categories or TARGET_ARXIV_CATEGORIES
            logger.info("Collecting arXiv papers — categories=%s", categories)
            arxiv_collector = ArxivClient(settings)
            arxiv_papers = await arxiv_collector.collect(categories, year_start, year_end)
            logger.info("Collected %d arXiv papers.", len(arxiv_papers))
            existing_ids = {p.paper_id for p in papers}
            papers = papers + [p for p in arxiv_papers if p.paper_id not in existing_ids]
            logger.info("Total after merge: %d papers.", len(papers))

        if not papers:
            logger.warning("No papers collected. Check venues/year range or API key.")
            return

        # 2a. Citation Graph
        service = CitationGraphService(repo)
        service.build_citation_graph(papers)
        logger.info("Citation graph ingestion complete.")

        # 2b. Method Evolution Graph (optional)
        if args.method_graph:
            _build_method_graph(repo, papers, args.llm_model, settings)

    finally:
        driver.close()


if __name__ == "__main__":
    asyncio.run(main())
