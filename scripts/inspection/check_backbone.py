"""
Quick manual check for the Layer C ranking pipeline (Step 4.3).

Runs the full pipeline: hybrid retrieval → centrality ranking → embedding ranking
→ combined ranking + backbone extraction, then prints results.

Usage:
  python scripts/inspection/check_backbone.py --query "attention mechanism transformer"
  python scripts/inspection/check_backbone.py --query "diffusion models" --top-k 5 --alpha 0.6
  python scripts/inspection/check_backbone.py --query "BERT language model" --top-k 8 --hops 2
"""

import argparse
import logging
import sys

from neo4j import GraphDatabase
from openai import OpenAI

from aievograph.config.settings import get_settings
from aievograph.domain.services.centrality_ranking_service import CentralityRankingService
from aievograph.domain.services.combined_ranking_service import CombinedRankingService
from aievograph.domain.services.embedding_ranking_service import EmbeddingRankingService
from aievograph.domain.services.hybrid_retrieval_service import HybridRetrievalService
from aievograph.domain.services.vector_retrieval_service import VectorRetrievalService
from aievograph.infrastructure.neo4j_centrality_repository import Neo4jCentralityRepository
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository
from aievograph.infrastructure.neo4j_paper_embedding_repository import Neo4jPaperEmbeddingRepository
from aievograph.infrastructure.neo4j_subgraph_edge_repository import Neo4jSubgraphEdgeRepository
from aievograph.infrastructure.neo4j_vector_repository import Neo4jVectorRepository
from aievograph.infrastructure.openai_embedding_client import OpenAIEmbeddingClient

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check backbone extraction pipeline (Layer C Step 4.3).")
    parser.add_argument("--query", required=True, help="Search query text.")
    parser.add_argument("--top-k", type=int, default=10, help="Number of top papers (default: 10).")
    parser.add_argument("--hops", type=int, default=1, help="Graph hop depth for retrieval (default: 1).")
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.5,
        help="Weight for centrality score in [0, 1]; (1-alpha) goes to semantic (default: 0.5).",
    )
    parser.add_argument(
        "--query-type",
        choices=["semantic", "structural", "balanced"],
        default="balanced",
        help="Hybrid retrieval weight preset (default: balanced).",
    )
    return parser.parse_args()


def _print_section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print("=" * 65)


def _print_scored_paper(rank: int, sp) -> None:
    p = sp.paper
    authors = ", ".join(a.name for a in p.authors[:3])
    if len(p.authors) > 3:
        authors += f" +{len(p.authors) - 3}"
    print(f"  [{rank:2d}] score={sp.score:.4f}")
    print(f"        title : {p.title[:70]}")
    print(f"        id    : {p.paper_id}")
    print(f"        year  : {p.publication_year}  venue: {p.venue or '-'}")
    print(f"        authors: {authors or '-'}")


def _print_centrality_scores(centrality_breakdown: list, papers_map: dict) -> None:
    """Print per-paper centrality breakdown."""
    for i, cs in enumerate(centrality_breakdown, 1):
        title = papers_map.get(cs.paper_id, {})
        title_str = (title.title[:55] + "…") if title and len(title.title) > 55 else (title.title if title else "?")
        print(
            f"  [{i:2d}] pagerank={cs.pagerank:.4f}  betweenness={cs.betweenness:.4f}"
            f"  combined={cs.combined_score:.4f}"
        )
        print(f"        {cs.paper_id}  {title_str}")


def main() -> None:
    args = parse_args()
    settings = get_settings()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        # Infrastructure
        graph_repo = Neo4jGraphRepository(driver)
        vector_repo = Neo4jVectorRepository(driver)
        centrality_repo = Neo4jCentralityRepository(driver)
        paper_embedding_repo = Neo4jPaperEmbeddingRepository(driver)
        subgraph_edge_repo = Neo4jSubgraphEdgeRepository(driver)
        embedding_client = OpenAIEmbeddingClient(api_key=settings.openai_api_key)

        # Services
        vector_service = VectorRetrievalService(embedding_client, vector_repo)
        hybrid_service = HybridRetrievalService(vector_service, graph_repo)
        centrality_svc = CentralityRankingService(centrality_repo)
        embedding_svc = EmbeddingRankingService(embedding_client, paper_embedding_repo)
        combined_svc = CombinedRankingService(centrality_svc, embedding_svc, subgraph_edge_repo)

        print(f"\nQuery      : {args.query!r}")
        print(f"top_k      : {args.top_k}")
        print(f"hops       : {args.hops}")
        print(f"alpha      : {args.alpha}  (centrality weight)")
        print(f"query_type : {args.query_type}")

        # ── Step 3.3: Hybrid Retrieval (subgraph input) ───────────────────
        _print_section("Step 3.3 — Hybrid Retrieval (subgraph input for Layer C)")
        subgraph = hybrid_service.search(
            args.query,
            query_type=args.query_type,
            top_k=args.top_k * 2,  # retrieve more candidates for ranking to filter
            hops=args.hops,
        )
        if not subgraph.papers:
            print("  (no results — check Neo4j connection and data)")
            return
        print(f"  Retrieved {len(subgraph.papers)} candidate papers for ranking.")

        # ── Step 4.1: Centrality Breakdown ────────────────────────────────
        _print_section("Step 4.1 — Centrality Scores (PageRank + Betweenness)")
        centrality_breakdown = centrality_svc.score_breakdown(subgraph)
        papers_map = {sp.paper.paper_id: sp.paper for sp in subgraph.papers}
        _print_centrality_scores(centrality_breakdown, papers_map)

        # ── Step 4.2: Semantic Similarity Ranking ─────────────────────────
        _print_section("Step 4.2 — Semantic Similarity Ranking")
        semantic_results = embedding_svc.rank(args.query, subgraph)
        if not semantic_results:
            print("  (no results)")
        for i, sp in enumerate(semantic_results[: args.top_k], 1):
            _print_scored_paper(i, sp)

        # ── Step 4.3: Combined Ranking + Backbone Extraction ─────────────
        _print_section(f"Step 4.3 — Combined Ranking (alpha={args.alpha}) + Backbone Extraction")
        result = combined_svc.rank(
            query=args.query,
            subgraph=subgraph,
            alpha=args.alpha,
            top_k=args.top_k,
        )

        print(f"\n  Top-{args.top_k} Papers (centrality × {args.alpha} + semantic × {1 - args.alpha}):")
        if not result.top_papers:
            print("  (no results)")
        for i, sp in enumerate(result.top_papers, 1):
            _print_scored_paper(i, sp)

        # ── Backbone Paths ────────────────────────────────────────────────
        print(f"\n  Backbone Paths ({len(result.backbone_paths)} paths found):")
        if not result.backbone_paths:
            print("  (none — no citation edges between top-k papers, or all papers are isolated)")
        else:
            top_papers_map = {sp.paper.paper_id: sp.paper for sp in result.top_papers}
            for pi, path in enumerate(result.backbone_paths, 1):
                print(f"\n  Path {pi} ({len(path)} papers, oldest → newest):")
                for step, pid in enumerate(path):
                    paper = top_papers_map.get(pid)
                    title_str = (paper.title[:55] + "…") if paper and len(paper.title) > 55 else (paper.title if paper else pid)
                    year_str = str(paper.publication_year) if paper else "?"
                    arrow = "  →" if step > 0 else "   "
                    print(f"    {arrow} [{year_str}] {pid}")
                    print(f"           {title_str}")

    except Exception:
        logging.getLogger(__name__).exception("Backbone check failed.")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
