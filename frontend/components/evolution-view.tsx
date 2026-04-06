"use client";

import { useState } from "react";
import { ChevronDownIcon, GitBranchIcon } from "lucide-react";

import { traceEvolution, type EvolutionResponse } from "@/lib/api";
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
import { GraphViewPanel } from "@/components/graph-view-panel";

const YEAR_MIN = 2011;
const YEAR_MAX = 2025;

// ---------------------------------------------------------------------------
// Yearly usage mini-chart (SVG bar chart)
// ---------------------------------------------------------------------------

interface YearlyBarChartProps {
  yearly_counts: Record<string, number>;
}

function YearlyBarChart({ yearly_counts }: YearlyBarChartProps) {
  const entries = Object.entries(yearly_counts).sort((a, b) => Number(a[0]) - Number(b[0]));
  if (entries.length === 0) return null;

  const BAR_W = 24;
  const BAR_GAP = 4;
  const PAD_X = 8;
  const PAD_T = 16;
  const PAD_B = 20;
  const CHART_H = 80;

  const maxCount = Math.max(...entries.map(([, v]) => v), 1);
  const svgW = PAD_X * 2 + entries.length * (BAR_W + BAR_GAP) - BAR_GAP;
  const svgH = CHART_H + PAD_T + PAD_B;

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} style={{ display: "block" }}>
        {entries.map(([year, count], i) => {
          const x = PAD_X + i * (BAR_W + BAR_GAP);
          const h = (count / maxCount) * CHART_H;
          const y = PAD_T + CHART_H - h;
          return (
            <g key={year}>
              <rect x={x} y={y} width={BAR_W} height={h} rx={2} fill="hsl(220 70% 65%)" />
              {/* Count label above bar */}
              {h > 0 && (
                <text
                  x={x + BAR_W / 2}
                  y={y - 2}
                  textAnchor="middle"
                  dominantBaseline="auto"
                  fontSize={7}
                  fill="hsl(220 14% 40%)"
                >
                  {count}
                </text>
              )}
              {/* Year label below bar */}
              <text
                x={x + BAR_W / 2}
                y={PAD_T + CHART_H + 5}
                textAnchor="middle"
                dominantBaseline="hanging"
                fontSize={8}
                fill="hsl(220 14% 50%)"
              >
                {year}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Influence score table
// ---------------------------------------------------------------------------

interface InfluenceTableProps {
  influence_scores: Record<string, number>;
}

function InfluenceTable({ influence_scores }: InfluenceTableProps) {
  const entries = Object.entries(influence_scores).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-1.5 pr-3 font-medium">Method</th>
            <th className="py-1.5 font-medium text-right">Influence</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([method, score]) => (
            <tr key={method} className="border-b last:border-0">
              <td className="py-1.5 pr-3 font-medium">{method}</td>
              <td className="py-1.5 text-right font-mono">{score.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function EvolutionView() {
  const [methodName, setMethodName] = useState("");
  const [yearRange, setYearRange] = useState<number[]>([2015, 2024]);
  const [showDesc, setShowDesc] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<EvolutionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleDesc(key: string) {
    setShowDesc((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!methodName.trim()) {
      setError("Method name is required.");
      return;
    }
    if (yearRange[0] > yearRange[1]) {
      setError("Start year must be ≤ end year.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await traceEvolution({
        method_name: methodName.trim(),
        start_year: yearRange[0],
        end_year: yearRange[1],
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evolution trace failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr] lg:items-start">
      {/* ── Left: Query Form + Score Cards ── */}
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitBranchIcon className="size-4" />
              Method Evolution Path
            </CardTitle>
            <CardDescription>
              Search for a method and trace how it evolved — which methods it extended,
              improved, or replaced over time.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              {/* Method name */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="method">Method Name</Label>
                  <button
                    type="button"
                    onClick={() => toggleDesc("method")}
                    className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Help{" "}
                    <ChevronDownIcon
                      className={[
                        "size-3 transition-transform",
                        showDesc["method"] ? "rotate-180" : "",
                      ].join(" ")}
                    />
                  </button>
                </div>
                {showDesc["method"] && (
                  <p className="text-xs text-muted-foreground">
                    A method name to search. Partial matches are supported —
                    e.g. "Transformer" will match "Vision Transformer", "Transformer-XL", etc.
                  </p>
                )}
                <Input
                  id="method"
                  placeholder="e.g. Transformer, LoRA, Diffusion"
                  value={methodName}
                  onChange={(e) => setMethodName(e.target.value)}
                  required
                />
              </div>

              {/* Year range */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Label>Time Range</Label>
                    <button
                      type="button"
                      onClick={() => toggleDesc("yearRange")}
                      className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Help{" "}
                      <ChevronDownIcon
                        className={[
                          "size-3 transition-transform",
                          showDesc["yearRange"] ? "rotate-180" : "",
                        ].join(" ")}
                      />
                    </button>
                  </div>
                  <span className="text-sm font-medium tabular-nums">
                    {yearRange[0]} – {yearRange[1]}
                  </span>
                </div>
                {showDesc["yearRange"] && (
                  <p className="text-xs text-muted-foreground">
                    Restrict the evolution path analysis to this publication year range.
                  </p>
                )}
                <Slider
                  min={YEAR_MIN}
                  max={YEAR_MAX}
                  step={1}
                  value={yearRange}
                  onValueChange={(val) => {
                    const v = Array.isArray(val) ? [...val] : [val];
                    const lo = v[0] ?? yearRange[0];
                    const hi = v[1] ?? yearRange[1];
                    if (lo <= hi) setYearRange([lo, hi]);
                  }}
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{YEAR_MIN}</span>
                  <span>{YEAR_MAX}</span>
                </div>
              </div>

              <Button type="submit" disabled={loading || !methodName.trim()}>
                <GitBranchIcon />
                {loading ? "Tracing…" : "Trace Evolution"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {result && (
          <>
            <Card>
              <CardHeader>
                <CardTitle>
                  Yearly Usage —{" "}
                  <span className="font-mono text-muted-foreground">{result.method_name}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <YearlyBarChart yearly_counts={result.yearly_counts} />
              </CardContent>
            </Card>

            {Object.keys(result.influence_scores).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Influence Scores</CardTitle>
                  <CardDescription>
                    Combined trend + breakthrough signal per method in the evolution subgraph.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <InfluenceTable influence_scores={result.influence_scores} />
                </CardContent>
              </Card>
            )}
          </>
        )}

        {!loading && !result && !error && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border bg-muted/40 py-16 text-muted-foreground">
            <GitBranchIcon className="size-8 opacity-40" />
            <p className="text-sm">Enter a method name to trace its evolution.</p>
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center rounded-xl border bg-muted/40 py-16 text-sm text-muted-foreground">
            Tracing evolution path…
          </div>
        )}
      </div>

      {/* ── Right: Evolution DAG via GraphViewPanel ── */}
      <GraphViewPanel lineageResult={null} evolutionResult={result} />
    </div>
  );
}
