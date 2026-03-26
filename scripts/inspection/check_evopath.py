"""
Quick manual check for the Layer D analytical pipeline (Step 5.1 → 5.2 → 5.3).

Given a time window, the script:
  1. Discovers active methods and their papers from Neo4j (within the window)
  2. Step 5.1 — Breakthrough Detection: finds papers where citation bursts / centrality
     shifts occurred (structural inflection points)
  3. Step 5.2 — Trend Momentum: ranks methods by CAGR / entropy / velocity
  4. Step 5.3 — Evolution Path: extracts research lineage paths weighted by the above

Usage:
  python scripts/inspection/check_evopath.py --year-start 2015 --year-end 2023
  python scripts/inspection/check_evopath.py --year-start 2018 --year-end 2023 --top-k 10
  python scripts/inspection/check_evopath.py --year-start 2016 --year-end 2022 --method-limit 50
"""

import argparse
import logging
import sys
from datetime import datetime

from neo4j import GraphDatabase

from aievograph.config.settings import get_settings
from aievograph.domain.services.breakthrough_detection_service import BreakthroughDetectionService
from aievograph.domain.services.evolution_path_service import EvolutionPathService
from aievograph.domain.services.trend_momentum_service import TrendMomentumService
from aievograph.infrastructure.neo4j_citation_time_series_repository import (
    Neo4jCitationTimeSeriesRepository,
)
from aievograph.infrastructure.neo4j_method_evolution_repository import (
    Neo4jMethodEvolutionRepository,
)
from aievograph.infrastructure.neo4j_method_trend_repository import Neo4jMethodTrendRepository

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

_CURRENT_YEAR = datetime.now().year

# ---------------------------------------------------------------------------
# Neo4j discovery queries
# ---------------------------------------------------------------------------

# Methods active in the window, ordered by usage count descending.
_ACTIVE_METHODS = """
MATCH (p:Paper)-[:USES]->(m:Method)
WHERE p.publication_year >= $year_start
  AND p.publication_year <= $year_end
WITH m.name AS method_name, count(p) AS usage_count
ORDER BY usage_count DESC
LIMIT $limit
RETURN method_name
"""

# Papers that use any of the given methods and were published in the window.
_PAPERS_FOR_METHODS = """
MATCH (p:Paper)-[:USES]->(m:Method)
WHERE m.name IN $method_names
  AND p.publication_year >= $year_start
  AND p.publication_year <= $year_end
RETURN DISTINCT p.paper_id AS paper_id
"""

# Paper titles for display (paper_ids → title + year).
_PAPER_META = """
MATCH (p:Paper)
WHERE p.paper_id IN $paper_ids
RETURN p.paper_id AS paper_id, p.title AS title, p.publication_year AS year
"""


def _discover_active_methods(driver, year_start: int, year_end: int, limit: int) -> list[str]:
    with driver.session() as session:
        return [r["method_name"] for r in session.run(
            _ACTIVE_METHODS, year_start=year_start, year_end=year_end, limit=limit
        )]


def _get_papers_for_methods(driver, method_names: list[str], year_start: int, year_end: int) -> list[str]:
    if not method_names:
        return []
    with driver.session() as session:
        return [r["paper_id"] for r in session.run(
            _PAPERS_FOR_METHODS, method_names=method_names,
            year_start=year_start, year_end=year_end,
        )]


def _get_paper_meta(driver, paper_ids: list[str]) -> dict[str, dict]:
    if not paper_ids:
        return {}
    with driver.session() as session:
        return {
            r["paper_id"]: {"title": r["title"], "year": r["year"]}
            for r in session.run(_PAPER_META, paper_ids=paper_ids)
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect Layer D analytical pipeline — structural inflection points + trending methods."
    )
    parser.add_argument("--year-start", type=int, required=True, help="Analysis window start year.")
    parser.add_argument("--year-end", type=int, required=True, help="Analysis window end year.")
    parser.add_argument(
        "--top-k", type=int, default=10,
        help="Max results to show per step (default: 10).",
    )
    parser.add_argument(
        "--recent-years", type=int, default=5,
        help="Recent window width for trend momentum (default: 5).",
    )
    parser.add_argument(
        "--method-limit", type=int, default=100,
        help="Max number of active methods to consider from Neo4j (default: 100).",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.5,
        help="Blend weight: trend vs breakthrough influence in evolution paths (default: 0.5).",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print("=" * 65)


def _print_breakthrough(rank: int, bc, paper_meta: dict) -> None:
    meta = paper_meta.get(bc.paper_id, {})
    title = meta.get("title", "")
    year = meta.get("year", "?")
    title_str = (title[:60] + "…") if len(title) > 60 else title
    print(
        f"  [{rank:2d}] breakthrough={bc.breakthrough_score:.4f}"
        f"  burst={bc.burst_score:.4f}  shift={bc.centrality_shift:.4f}"
        f"  year={year}"
    )
    print(f"        {title_str or bc.paper_id}")


def _print_trend(rank: int, ts) -> None:
    print(
        f"  [{rank:2d}] trend={ts.trend_score:.4f}"
        f"  cagr={ts.cagr_score:.4f}  entropy={ts.entropy_score:.4f}"
        f"  velocity={ts.adoption_velocity_score:.4f}"
    )
    print(f"        {ts.method_name}")


def _print_evo_path(rank: int, ep) -> None:
    print(f"\n  Path {rank}  mean_influence={ep.mean_influence:.4f}  length={len(ep.path)}")
    branch_set = set(ep.branch_points)
    rels = [""] + ep.relation_types
    for i, (method, rel) in enumerate(zip(ep.path, rels)):
        prefix = "   " if i == 0 else f"  →[{rel}]"
        branch_tag = "  ★ branch" if method in branch_set else ""
        score = ep.influence_scores.get(method, 0.0)
        print(f"    {prefix:18s} {method}  (influence={score:.4f}){branch_tag}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    settings = get_settings()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        print(f"\nWindow       : {args.year_start} – {args.year_end}")
        print(f"top_k        : {args.top_k}  recent_years: {args.recent_years}  alpha: {args.alpha}")
        print(f"method_limit : {args.method_limit}")

        # ── Discover active methods in the window ─────────────────────────
        print(f"\nDiscovering active methods in {args.year_start}–{args.year_end} …")
        method_names = _discover_active_methods(
            driver, args.year_start, args.year_end, args.method_limit
        )
        if not method_names:
            print("No active methods found — check Neo4j data and year range.")
            return
        print(f"Found {len(method_names)} active methods.")

        # ── Discover papers using those methods ───────────────────────────
        paper_ids = _get_papers_for_methods(
            driver, method_names, args.year_start, args.year_end
        )
        print(f"Found {len(paper_ids)} associated papers.")

        # ── Step 5.1: Breakthrough Detection ─────────────────────────────
        _section("Step 5.1 — Structural Inflection Points (Kleinberg burst + centrality shift)")

        if not paper_ids:
            print("  (no papers — skipping)")
            breakthrough_candidates = []
        else:
            citation_ts_repo = Neo4jCitationTimeSeriesRepository(driver)
            breakthrough_svc = BreakthroughDetectionService(citation_ts_repo)
            breakthrough_candidates = breakthrough_svc.detect(
                paper_ids=paper_ids,
                year_start=args.year_start,
                year_end=args.year_end,
                top_k=args.top_k,
            )

            top_paper_ids = [bc.paper_id for bc in breakthrough_candidates]
            paper_meta = _get_paper_meta(driver, top_paper_ids)

            print(f"  Top-{args.top_k} breakthrough papers (citation burst + centrality shift):")
            if not breakthrough_candidates:
                print("  (none — no citation data in window or all scores are 0)")
            for i, bc in enumerate(breakthrough_candidates, 1):
                _print_breakthrough(i, bc, paper_meta)

        # ── Step 5.2: Trend Momentum Score ───────────────────────────────
        _section("Step 5.2 — Trending Methods (CAGR + Venue Entropy + Adoption Velocity)")

        trend_repo = Neo4jMethodTrendRepository(driver)
        trend_svc = TrendMomentumService(trend_repo)
        trend_scores = trend_svc.score(
            method_names=method_names,
            year_end=args.year_end,
            recent_years=args.recent_years,
            top_k=args.top_k,
        )

        print(f"  Top-{args.top_k} trending methods:")
        if not trend_scores:
            print("  (none — no USES edges in window)")
        for i, ts in enumerate(trend_scores, 1):
            _print_trend(i, ts)

        # ── Step 5.3: Evolution Path Extraction ──────────────────────────
        _section("Step 5.3 — Evolution Paths (research lineage in Method Evolution Graph)")

        evo_repo = Neo4jMethodEvolutionRepository(driver)
        evo_svc = EvolutionPathService(evo_repo)
        evolution_paths = evo_svc.extract(
            method_names=method_names,
            trend_scores=trend_scores,
            breakthrough_candidates=breakthrough_candidates,
            top_k=args.top_k,
            alpha=args.alpha,
        )

        print(f"  Evolution paths found: {len(evolution_paths)}")
        if not evolution_paths:
            print(
                "  (none — no IMPROVES/EXTENDS/REPLACES edges between active methods,\n"
                "   or all paths have length < 2)"
            )
        for i, ep in enumerate(evolution_paths, 1):
            _print_evo_path(i, ep)

    except Exception:
        logging.getLogger(__name__).exception("Evolution path check failed.")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
