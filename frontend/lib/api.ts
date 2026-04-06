/**
 * AI EvoGraph API client.
 * Typed wrappers around the FastAPI backend endpoints.
 */

// Empty string means relative URL — Next.js rewrites proxy /api/* to the backend.
// Set NEXT_PUBLIC_API_URL to override (e.g. direct backend access in tests).
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

async function post<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  const data: unknown = await res.json();
  // Guard against non-object responses (e.g. HTML error pages, null, bare arrays).
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    throw new Error(`API error: unexpected response shape from ${path}`);
  }
  return data as TRes;
}

// ---------------------------------------------------------------------------
// Lineage — Research Lineage Exploration
// ---------------------------------------------------------------------------

export type QueryType = "semantic" | "structural" | "balanced";

export interface LineageRequest {
  seed: string;
  hop_depth?: number;       // default 2
  start_year?: number;
  end_year?: number;
  top_k?: number;           // default 20
  query_type?: QueryType;   // default "balanced"
}

export interface PaperNode {
  paper_id: string;
  title: string;
  year: number | null;
  authors: string[];
  citation_count: number;
  score: number | null;
  semantic_similarity: number | null;
  graph_proximity: number | null;
}

export interface CitationEdge {
  source_id: string;
  target_id: string;
}

export interface LineageResponse {
  papers: PaperNode[];
  edges: CitationEdge[];
  total: number;
}

export function exploreLineage(req: LineageRequest): Promise<LineageResponse> {
  return post<LineageRequest, LineageResponse>("/api/lineage", req);
}

// ---------------------------------------------------------------------------
// Breakthrough — Breakthrough Detection
// ---------------------------------------------------------------------------

export interface BreakthroughRequest {
  field: string;
  start_year: number;
  end_year: number;
  top_k?: number;  // default 10
}

export interface BreakthroughCandidate {
  paper_id: string;
  title: string;
  year: number | null;
  burst_score: number;
  centrality_shift: number;
  composite_score: number;
}

export interface BreakthroughResponse {
  candidates: BreakthroughCandidate[];
  total: number;
}

export function detectBreakthroughs(
  req: BreakthroughRequest
): Promise<BreakthroughResponse> {
  return post<BreakthroughRequest, BreakthroughResponse>("/api/breakthrough", req);
}

// ---------------------------------------------------------------------------
// Trend — Trending Methods Discovery
// ---------------------------------------------------------------------------

export interface TrendRequest {
  start_year: number;
  end_year: number;
  top_k?: number;  // default 30
}

export interface TrendMethodResult {
  method_name: string;
  cagr: number;
  entropy: number;
  adoption_velocity: number;
  momentum_score: number;
  yearly_counts: Record<string, number>;
}

export interface TrendResponse {
  start_year: number;
  end_year: number;
  methods: TrendMethodResult[];
}

export function discoverTrending(req: TrendRequest): Promise<TrendResponse> {
  return post<TrendRequest, TrendResponse>("/api/trend", req);
}

// ---------------------------------------------------------------------------
// Evolution — Method Evolution Path
// ---------------------------------------------------------------------------

export interface EvolutionRequest {
  method_name: string;
  start_year: number;
  end_year: number;
}

export interface EvolutionStep {
  from_method: string;
  to_method: string;
  relation_type: string;
  year: number | null;
}

export interface EvolutionResponse {
  method_name: string;
  evolution_path: EvolutionStep[];
  yearly_counts: Record<string, number>;
  influence_scores: Record<string, number>;
}

export function traceEvolution(req: EvolutionRequest): Promise<EvolutionResponse> {
  return post<EvolutionRequest, EvolutionResponse>("/api/evolution", req);
}
