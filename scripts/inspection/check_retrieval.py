"""
Quick manual check for the three retrieval steps (Layer B).

Usage:
  python scripts/inspection/check_retrieval.py --query "attention mechanism transformer"
  python scripts/inspection/check_retrieval.py --query "diffusion models" --top-k 5 --hops 2
  python scripts/inspection/check_retrieval.py --query "reinforcement learning" --query-type structural
"""

import argparse
import logging
import sys

from neo4j import GraphDatabase
from openai import OpenAI

from aievograph.config.settings import get_settings
from aievograph.domain.services.graph_retrieval_service import GraphRetrievalService
from aievograph.domain.services.hybrid_retrieval_service import HybridRetrievalService
from aievograph.domain.services.vector_retrieval_service import VectorRetrievalService
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository
from aievograph.infrastructure.neo4j_vector_repository import Neo4jVectorRepository
from aievograph.infrastructure.openai_embedding_client import OpenAIEmbeddingClient

logging.basicConfig(
    level=logging.WARNING,  # suppress INFO noise from services
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check retrieval pipeline (Layer B).")
    parser.add_argument("--query", required=True, help="Search query text.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5).")
    parser.add_argument("--hops", type=int, default=1, help="Graph hop depth (default: 1).")
    parser.add_argument(
        "--query-type",
        choices=["semantic", "structural", "balanced"],
        default="balanced",
        help="Hybrid weight preset (default: balanced).",
    )
    return parser.parse_args()


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _print_paper(rank: int, paper, score: float | None = None) -> None:
    score_str = f"  score={score:.4f}" if score is not None else ""
    print(f"  [{rank}]{score_str}")
    print(f"       title : {paper.title}")
    print(f"       id    : {paper.paper_id}")
    print(f"       year  : {paper.publication_year}  venue: {paper.venue or '-'}")
    authors = ", ".join(a.name for a in paper.authors[:3])
    if len(paper.authors) > 3:
        authors += f" +{len(paper.authors) - 3}"
    print(f"       authors: {authors or '-'}")


def main() -> None:
    args = parse_args()
    settings = get_settings()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        graph_repo = Neo4jGraphRepository(driver)
        vector_repo = Neo4jVectorRepository(driver)
        embedding_client = OpenAIEmbeddingClient(api_key=settings.openai_api_key)

        vector_service = VectorRetrievalService(embedding_client, vector_repo)
        graph_service = GraphRetrievalService(graph_repo)
        hybrid_service = HybridRetrievalService(vector_service, graph_repo)

        print(f"\nQuery      : {args.query!r}")
        print(f"top_k      : {args.top_k}")
        print(f"hops       : {args.hops}")
        print(f"query_type : {args.query_type}")

        # ── Step 3.1: Vector Retrieval ────────────────────────────────
        _print_section("Step 3.1 — Vector Retrieval (semantic similarity)")
        vector_results = vector_service.search(args.query, top_k=args.top_k)
        if not vector_results:
            print("  (no results)")
        for i, sp in enumerate(vector_results, 1):
            _print_paper(i, sp.paper, sp.score)

        # ── Step 3.2: Graph Retrieval ─────────────────────────────────
        _print_section("Step 3.2 — Graph Retrieval (citation neighborhood)")
        if not vector_results:
            print("  (skipped — no vector seeds)")
        else:
            seed = vector_results[0].paper
            print(f"  Seed: {seed.paper_id!r}  ({seed.title[:60]})")
            graph_results = graph_service.expand_from_id(seed.paper_id, hops=args.hops)
            if not graph_results:
                print("  (no neighbors found)")
            for i, paper in enumerate(graph_results[: args.top_k], 1):
                _print_paper(i, paper)

        # ── Step 3.3: Hybrid Retrieval ────────────────────────────────
        _print_section(f"Step 3.3 — Hybrid Retrieval (query_type={args.query_type!r})")
        subgraph = hybrid_service.search(
            args.query,
            query_type=args.query_type,
            top_k=args.top_k,
            hops=args.hops,
        )
        if not subgraph.papers:
            print("  (no results)")
        for i, sp in enumerate(subgraph.papers, 1):
            _print_paper(i, sp.paper, sp.score)

    except Exception:
        logging.getLogger(__name__).exception("Retrieval check failed.")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
