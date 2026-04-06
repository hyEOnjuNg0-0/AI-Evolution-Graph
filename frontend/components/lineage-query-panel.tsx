"use client";

import { useState } from "react";
import { SearchIcon, BookOpenIcon, ArrowRightIcon, ChevronDownIcon } from "lucide-react";

import { exploreLineage, type LineageResponse, type PaperNode, type QueryType } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";

const YEAR_MIN = 2011;
const YEAR_MAX = 2025;

const QUERY_TYPE_OPTIONS: { value: QueryType; label: string; description: string }[] = [
  { value: "semantic",   label: "Semantic",   description: "α=0.9 · β=0.1 — meaning-first" },
  { value: "balanced",   label: "Balanced",   description: "α=0.5 · β=0.5 — balanced" },
  { value: "structural", label: "Structural", description: "α=0.1 · β=0.9 — citation-first" },
];

interface LineageQueryPanelProps {
  /** Called with the API response each time a search completes successfully. */
  onResult?: (result: LineageResponse) => void;
  /** Called when the user selects (or deselects) a paper from the results list. */
  onSelectPaper?: (paper: PaperNode | null) => void;
  /** Currently selected paper ID (controlled from parent). */
  selectedPaperId?: string | null;
}

export function LineageQueryPanel({ onResult, onSelectPaper, selectedPaperId }: LineageQueryPanelProps = {}) {
  const [seed, setSeed] = useState("");
  const [queryType, setQueryType] = useState<QueryType>("balanced");
  const [hopDepth, setHopDepth] = useState(2);
  const [yearRange, setYearRange] = useState<number[]>([2018, 2024]);
  const [topK, setTopK] = useState(10);
  const [showDesc, setShowDesc] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LineageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleDesc(key: string) {
    setShowDesc((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!seed.trim()) return;
    if (yearRange[0] > yearRange[1]) {
      setError("Start year must be ≤ end year.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await exploreLineage({
        seed: seed.trim(),
        query_type: queryType,
        hop_depth: hopDepth,
        start_year: yearRange[0],
        end_year: yearRange[1],
        top_k: topK,
      });
      setResult(data);
      onResult?.(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Query Form ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpenIcon className="size-4" />
            Research Lineage Exploration
          </CardTitle>
          <CardDescription>
            Enter a keyword or paper title to explore related research by semantic similarity and citation structure.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {/* Seed keyword */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="seed">Keyword / Paper Title</Label>
                <button type="button" onClick={() => toggleDesc("seed")} className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  Help <ChevronDownIcon className={["size-3 transition-transform", showDesc["seed"] ? "rotate-180" : ""].join(" ")} />
                </button>
              </div>
              {showDesc["seed"] && (
                <p className="text-xs text-muted-foreground">
                  A research topic, method name, or paper title. Used as a natural-language query — paper IDs are not supported.
                </p>
              )}
              <Input
                id="seed"
                placeholder="e.g. attention mechanism, diffusion models, transformer"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                required
              />
            </div>

            {/* Query type */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label>Query Type</Label>
                <button type="button" onClick={() => toggleDesc("queryType")} className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  Help <ChevronDownIcon className={["size-3 transition-transform", showDesc["queryType"] ? "rotate-180" : ""].join(" ")} />
                </button>
              </div>
              {showDesc["queryType"] && (
                <p className="text-xs text-muted-foreground">
                  Controls the balance between semantic similarity (α) and citation graph proximity (β). Use <strong>Semantic</strong> to prioritize meaning, <strong>Structural</strong> to follow citation links, or <strong>Balanced</strong> for both.
                </p>
              )}
              <div className="grid grid-cols-3 gap-2">
                {QUERY_TYPE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setQueryType(opt.value)}
                    className={[
                      "flex flex-col gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors",
                      queryType === opt.value
                        ? "border-ring bg-accent text-accent-foreground"
                        : "border-border hover:bg-muted",
                    ].join(" ")}
                  >
                    <span className="text-sm font-medium">{opt.label}</span>
                    <span className="text-xs text-muted-foreground">{opt.description}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Hop depth */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label>Hop Depth</Label>
                  <button type="button" onClick={() => toggleDesc("hopDepth")} className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    Help <ChevronDownIcon className={["size-3 transition-transform", showDesc["hopDepth"] ? "rotate-180" : ""].join(" ")} />
                  </button>
                </div>
                <span className="text-sm font-medium tabular-nums">{hopDepth}</span>
              </div>
              {showDesc["hopDepth"] && (
                <p className="text-xs text-muted-foreground">
                  How many citation hops to expand from seed papers. 1 = direct citations only; higher values reach more distantly related work but increase response time.
                </p>
              )}
              <Slider
                min={1}
                max={5}
                value={[hopDepth]}
                onValueChange={(val) => { const v = Array.isArray(val) ? val : [val]; setHopDepth(v[0]); }}
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>1</span>
                <span>5</span>
              </div>
            </div>

            {/* Year range */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label>Time Range</Label>
                  <button type="button" onClick={() => toggleDesc("yearRange")} className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    Help <ChevronDownIcon className={["size-3 transition-transform", showDesc["yearRange"] ? "rotate-180" : ""].join(" ")} />
                  </button>
                </div>
                <span className="text-sm font-medium tabular-nums">
                  {yearRange[0]} – {yearRange[1]}
                </span>
              </div>
              {showDesc["yearRange"] && (
                <p className="text-xs text-muted-foreground">
                  Filter results to papers published within this year range.
                </p>
              )}
              <Slider
                min={YEAR_MIN}
                max={YEAR_MAX}
                step={1}
                value={yearRange}
                onValueChange={(val) => {
                  const v = Array.isArray(val) ? [...val] : [val];
                  if (v.length >= 2 && v[0] <= v[1]) setYearRange(v);
                }}
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{YEAR_MIN}</span>
                <span>{YEAR_MAX}</span>
              </div>
            </div>

            {/* Top K */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label>Top K Results</Label>
                  <button type="button" onClick={() => toggleDesc("topK")} className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    Help <ChevronDownIcon className={["size-3 transition-transform", showDesc["topK"] ? "rotate-180" : ""].join(" ")} />
                  </button>
                </div>
                <span className="text-sm font-medium tabular-nums">{topK}</span>
              </div>
              {showDesc["topK"] && (
                <p className="text-xs text-muted-foreground">
                  Maximum number of papers to return, ranked by score.
                </p>
              )}
              <Slider
                min={5}
                max={20}
                step={1}
                value={[topK]}
                onValueChange={(val) => { const v = Array.isArray(val) ? val : [val]; setTopK(v[0]); }}
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>5</span>
                <span>20</span>
              </div>
            </div>

            <Button type="submit" disabled={loading || !seed.trim()}>
              <SearchIcon />
              {loading ? "Searching..." : "Search"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* ── Error ── */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* ── Results ── */}
      {result && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{result.total}</span> papers
            &nbsp;·&nbsp;
            <span className="font-medium text-foreground">{result.edges.length}</span> citation edges
          </p>
          <div className="flex flex-col gap-2">
            {result.papers.map((paper, idx) => {
              const isSelected = paper.paper_id === selectedPaperId;
              return (
                <button
                  key={paper.paper_id}
                  type="button"
                  onClick={() => onSelectPaper?.(isSelected ? null : paper)}
                  className={[
                    "flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors w-full",
                    isSelected
                      ? "border-ring bg-accent text-accent-foreground"
                      : "border-border hover:bg-muted",
                  ].join(" ")}
                >
                  <span className="mt-0.5 shrink-0 text-xs font-mono text-muted-foreground w-5 text-right">
                    {idx + 1}
                  </span>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <p className="font-medium leading-snug line-clamp-2 text-sm">{paper.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {paper.authors.slice(0, 3).join(", ")}
                      {paper.authors.length > 3 ? " et al." : ""}
                      {paper.year ? ` · ${paper.year}` : ""}
                      {` · ${paper.citation_count.toLocaleString()} citations`}
                    </p>
                  </div>
                  {paper.score != null && (
                    <Badge variant="secondary" className="shrink-0 font-mono">
                      {paper.score.toFixed(3)}
                    </Badge>
                  )}
                </button>
              );
            })}
          </div>

          {result.edges.length > 0 && (
            <Card size="sm">
              <CardHeader>
                <CardTitle>Citation Edges</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-1">
                {result.edges.slice(0, 10).map((e, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
                    <span className="truncate max-w-40">{e.source_id}</span>
                    <ArrowRightIcon className="size-3 shrink-0" />
                    <span className="truncate max-w-40">{e.target_id}</span>
                  </div>
                ))}
                {result.edges.length > 10 && (
                  <p className="text-xs text-muted-foreground">
                    +{result.edges.length - 10} more edges
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
