# AI EvoGraph

> **Map how AI research evolves.** AI EvoGraph builds a Citation and Method Evolution Graph from thousands of AI papers, then quantifies research lineage, structural inflection points, and diffusion dynamics — making the invisible architecture of scientific progress visible.

---

## Why AI EvoGraph?

The AI field produces thousands of papers every year. Finding which papers **actually matter**, understanding *how methods build on each other*, and identifying **when paradigm shifts happen** — these tasks are nearly impossible to do by hand.

AI EvoGraph tackles this by combining **graph databases**, **LLM-based knowledge extraction**, and **multi-layer analytical algorithms** into a single pipeline:

| Problem | AI EvoGraph's Answer |
|---|---|
| Which papers are most influential in my topic? | Hybrid vector + graph retrieval → centrality-based ranking |
| When did a research breakthrough happen? | Kleinberg burst detection + centrality shift analysis |
| Which methods are gaining momentum right now? | CAGR + Shannon entropy + adoption velocity scoring |
| How did a technique evolve from its origins? | Method Evolution Graph path extraction |

---

## Architecture

The system is built as **five clean layers**, each depending only on the layer below it. Higher layers are never implemented until lower ones are fully tested.

```
┌─────────────────────────────────────────────┐
│  Layer E — Interface (FastAPI + Next.js)    │  ← REST API + Web UI
├─────────────────────────────────────────────┤
│  Layer D — Analytical                       │  ← Breakthrough / Trend / Evolution
├─────────────────────────────────────────────┤
│  Layer C — Ranking                          │  ← Top-k, backbone extraction
├─────────────────────────────────────────────┤
│  Layer B — Retrieval                        │  ← Vector, graph, hybrid search
├─────────────────────────────────────────────┤
│  Layer A — Knowledge Graph                  │  ← Citation + Method Evolution Graph
└─────────────────────────────────────────────┘
```

---

## Features & Algorithms

### Layer A — Knowledge Graph Construction

#### Temporal Citation Graph

Papers are collected from 15 major AI/ML venues (NeurIPS, ICML, ICLR, ACL, CVPR, etc.) via the **Semantic Scholar Bulk API**. Only papers in the top 20% of citation counts per year are retained — filtering noise while preserving influential work.

Each paper becomes a `(:Paper)` node in Neo4j. Citation relationships form directed edges:

```
(:Paper)-[:CITES]->(:Paper)
(:Paper)-[:WRITTEN_BY]->(:Author)
```

The `publication_year` property is indexed, enabling time-range queries across the graph.

#### Method Evolution Graph

Paper abstracts are fed to **GPT-4o** using a GraphRAG-style prompt that extracts method entities and their relationships in a single pass:

- **Entities**: `Method`, `Model`, `Technique`, `Framework` — each with a name and description
- **Relations**: `IMPROVES`, `EXTENDS`, `REPLACES` — with grounding evidence text
- **Gleaning**: after the first extraction, the LLM is asked if anything was missed, then re-extracts — improving recall

Extracted entities go through **Entity Normalization** before storage: string similarity clustering groups near-duplicate names (e.g. "BERT", "bert-base", "BERT-large"), then an LLM resolves ambiguous clusters into a single canonical name. A persistent normalization map prevents redundant LLM calls on future runs.

The final graph schema:

```
(:Method)-[:IMPROVES|EXTENDS|REPLACES]->(:Method)
(:Paper)-[:USES]->(:Method)
```

---

### Layer B — Retrieval

#### Vector Retrieval

Paper abstracts are embedded with **OpenAI `text-embedding-3-small`** and stored in a **Neo4j Vector Index**. At query time, the query string is embedded and a cosine similarity search returns the top-k semantically closest papers.

#### Graph Retrieval

Starting from seed papers (e.g. top results from vector search), a **N-hop neighborhood expansion** traverses the citation graph in both directions using a Cypher query. Each discovered paper is returned with its hop distance from the nearest seed.

#### Hybrid Retrieval

Vector and graph signals are fused into a single score:

```
hybrid_score = α × semantic_similarity + β × graph_proximity
```

| Signal | How it's computed |
|---|---|
| `semantic_similarity` | Cosine similarity from vector search; 0.0 for papers found only via graph expansion |
| `graph_proximity` | `1.0 / hop_distance`; 1.0 for seed papers, 0.5 at 2 hops, 0.33 at 3 hops, etc. |

Three query modes adjust the weights automatically:

| `query_type` | α (semantic) | β (graph) |
|---|---|---|
| `semantic` | 0.9 | 0.1 |
| `structural` | 0.1 | 0.9 |
| `balanced` | 0.5 | 0.5 |

---

### Layer C — Ranking

#### Centrality-based Ranking

Using **Neo4j Graph Data Science (GDS)**, two centrality metrics are computed on the retrieved subgraph:

- **PageRank**: measures global influence — papers cited by many other important papers score higher
- **Betweenness Centrality**: measures bridging importance — papers that connect otherwise separate clusters score higher

#### Embedding Similarity Ranking

The query embedding is compared against every paper embedding in the subgraph using cosine similarity. Scores are min-max normalized to [0, 1].

#### Combined Ranking & Backbone Extraction

Centrality and semantic scores are normalized independently, then combined:

```
final_score = w_centrality × centrality_score + w_semantic × semantic_score
```

**Backbone extraction** then prunes the subgraph to keep only the edges that form the most explanatory lineage paths — filtering out peripheral noise and surfacing the core research trajectory.

---

### Layer D — Analytical

#### Breakthrough Detection

Two signals are combined to detect when a paper represents a genuine paradigm shift:

1. **Kleinberg Burst Detection**: models citation counts as a two-state automaton. A "burst" is when the citation rate shifts to a significantly higher state, indicating sudden field-wide attention.

2. **Centrality Shift**: the change in a paper's PageRank between adjacent time windows. A paper that jumps in centrality (relative to the rest of the graph) is likely introducing or consolidating a major idea.

Papers are ranked by a combined burst + shift score.

#### Trend Momentum Score

For each method node in the Method Evolution Graph, three indicators are computed over a configurable time window:

| Indicator | Formula | What it captures |
|---|---|---|
| **CAGR** | `(count_end / count_start)^(1/years) − 1` | Compound annual growth rate of paper usage |
| **Diversity Entropy** | `−Σ p_i × log(p_i)` (Shannon entropy over venue distribution) | Breadth of adoption across research communities |
| **Adoption Velocity** | Rate at which new venues first adopt the method | How fast a method diffuses |

```
trend_score = α × CAGR + β × Entropy + γ × AdoptionVelocity
```

#### Evolution Path

Given a method name, the system:

1. Fuzzy-searches the Method Evolution Graph for matching nodes
2. Extracts all directed DAG paths using exhaustive DFS through `IMPROVES / EXTENDS / REPLACES` edges
3. Annotates each node with yearly paper counts (`USES` edges)
4. Identifies **branching points** — nodes with multiple outgoing evolution edges — which represent moments of methodological divergence

The result is a structured evolution DAG with influence scores at each node.

---

### Layer E — Interface

A **FastAPI** backend exposes four endpoints:

| Endpoint | Feature |
|---|---|
| `POST /api/lineage` | Research Lineage Exploration — retrieve + rank papers for a query |
| `POST /api/breakthrough` | Breakthrough Detection — find structural inflection points |
| `POST /api/trend` | Trending Methods Discovery — top-k methods by momentum score |
| `POST /api/evolution` | Method Evolution Path — trace how a technique evolved |

A **Next.js** frontend provides an interactive UI for each feature, including a citation graph SVG viewer and an evolution path DAG visualization.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Graph Database | Neo4j Aura + GDS | Citation/Method graph storage, Cypher queries, PageRank/Betweenness |
| Vector Search | Neo4j Vector Index | Embedding-based similarity search (no separate vector DB needed) |
| LLM | OpenAI GPT-4o | Method entity + relation extraction, entity normalization |
| Embeddings | OpenAI `text-embedding-3-small` | Paper and query embeddings |
| Orchestration | LangGraph | Multi-step RAG pipeline state management |
| Paper Data | Semantic Scholar Bulk API | Paper metadata, citation and reference data |
| Backend API | FastAPI | REST API for frontend communication |
| Frontend | Next.js + TailwindCSS + ShadCN | Web interface |
| Testing | pytest | TDD — unit and integration tests |

---

## Quick Start

**Requirements**: Python 3.11+, a [Neo4j Aura](https://neo4j.com/cloud/platform/aura-graph-database/) instance (free tier works)

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Configure environment
cp .env.example .env
# Fill in: OPENAI_API_KEY, SEMANTIC_SCHOLAR_API_KEY
#          NEO4J_URI (e.g. neo4j+s://<id>.databases.neo4j.io)
#          NEO4J_PASSWORD

# 3. Run tests
pytest

# 4. Start the API server
uvicorn src.aievograph.api.main:app --reload

# 5. Start the frontend
cd frontend && npm install && npm run dev
```

### Ingestion Pipeline

The ingestion script collects papers and builds the knowledge graph. All flags can be combined.

#### Data Sources

| Flag | Description |
|---|---|
| *(default)* | Collect from **Semantic Scholar** — 15 major AI/ML venues (NeurIPS, ICML, ICLR, ACL, CVPR, …) |
| `--venues A B` | Override default venue list (e.g. `--venues NeurIPS ICML ICLR`) |
| `--arxiv` | Also collect **arXiv preprints** for the configured categories (`cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, …) |
| `--arxiv-only` | Collect arXiv only, skip Semantic Scholar venue collection |
| `--arxiv-categories A B` | Override default arXiv categories |
| `--year-start YYYY` | Collection start year (default: 15 years ago, set via `COLLECT_YEAR_START` in `.env`) |
| `--year-end YYYY` | Collection end year (default: last year, set via `COLLECT_YEAR_END` in `.env`) |

#### What to Build

| Flag | Description |
|---|---|
| *(default)* | Build **Citation Graph** only (Paper nodes + CITES edges) |
| `--embed` | Also generate and store **paper embeddings** (needed for vector retrieval) |
| `--method-graph` | Also extract **Method Evolution Graph** from abstracts via LLM |
| `--embed --method-graph` | Build everything in one run |

#### Skip Collection (Backfill on Existing Data)

| Flag | Description |
|---|---|
| `--embed-only` | Skip collection — generate embeddings for papers already in Neo4j |
| `--method-graph-only` | Skip collection — build Method graph from papers already in Neo4j |

#### LLM Model

| Flag | Description |
|---|---|
| `--llm-model gpt-4o-mini` | Model used for method extraction and normalization (default: `gpt-4o-mini`) |
| `--llm-model gpt-4o` | Use the full GPT-4o for higher extraction quality (higher cost) |

#### Examples

```bash
# Full build: collect all venues + arXiv, embed, extract methods
python scripts/ingest.py --arxiv --embed --method-graph

# Collect specific venues, 2020–2024 only
python scripts/ingest.py --venues NeurIPS ICML ICLR --year-start 2020 --year-end 2024

# Papers already in Neo4j — just backfill embeddings and method graph
python scripts/ingest.py --embed-only
python scripts/ingest.py --method-graph-only

# Use higher-quality LLM for method extraction
python scripts/ingest.py --method-graph --llm-model gpt-4o

# Remove duplicate Method nodes after ingestion
python scripts/dedup_methods.py --dry-run   # preview what would be merged
python scripts/dedup_methods.py             # apply
```

---