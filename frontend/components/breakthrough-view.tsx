"use client";

import { useState } from "react";
import { ChevronDownIcon, ZapIcon } from "lucide-react";

import {
  detectBreakthroughs,
  type BreakthroughCandidate,
  type BreakthroughResponse,
} from "@/lib/api";
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

// ---------------------------------------------------------------------------
// Bar chart — composite_score per candidate (SVG, no external libs)
// ---------------------------------------------------------------------------

interface BreakthroughBarChartProps {
  candidates: BreakthroughCandidate[];
  selected: BreakthroughCandidate | null;
  onSelect: (c: BreakthroughCandidate | null) => void;
}

function BreakthroughBarChart({
  candidates,
  selected,
  onSelect,
}: BreakthroughBarChartProps) {
  if (candidates.length === 0) return null;

  const BAR_W = 36;
  const BAR_GAP = 8;
  const PAD_L = 40;
  const PAD_R = 16;
  const PAD_T = 20;
  const PAD_B = 28;
  const CHART_H = 140;

  const svgW = PAD_L + candidates.length * (BAR_W + BAR_GAP) - BAR_GAP + PAD_R;
  const svgH = CHART_H + PAD_T + PAD_B;

  const finiteScores = candidates
    .map((c) => c.composite_score)
    .filter((s) => Number.isFinite(s));
  const maxScore = finiteScores.length > 0 ? Math.max(...finiteScores, 0.01) : 0.01;

  function barY(score: number) {
    if (!Number.isFinite(score)) return PAD_T + CHART_H;
    return PAD_T + CHART_H - (score / maxScore) * CHART_H;
  }
  function barH(score: number) {
    if (!Number.isFinite(score)) return 0;
    return (score / maxScore) * CHART_H;
  }

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} style={{ display: "block" }}>
        {/* Axis line */}
        <line
          x1={PAD_L}
          y1={PAD_T + CHART_H}
          x2={svgW - PAD_R}
          y2={PAD_T + CHART_H}
          stroke="hsl(220 14% 80%)"
          strokeWidth={1}
        />

        {/* 0.5 guideline */}
        {maxScore > 0.5 && (
          <line
            x1={PAD_L - 4}
            y1={barY(0.5)}
            x2={svgW - PAD_R}
            y2={barY(0.5)}
            stroke="hsl(220 14% 85%)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}

        {/* Y-axis labels */}
        <text
          x={PAD_L - 6}
          y={PAD_T}
          textAnchor="end"
          dominantBaseline="hanging"
          fontSize={8}
          fill="hsl(220 14% 50%)"
        >
          {maxScore.toFixed(2)}
        </text>
        <text
          x={PAD_L - 6}
          y={PAD_T + CHART_H}
          textAnchor="end"
          dominantBaseline="auto"
          fontSize={8}
          fill="hsl(220 14% 50%)"
        >
          0
        </text>

        {/* Bars */}
        {candidates.map((c, i) => {
          const x = PAD_L + i * (BAR_W + BAR_GAP);
          const h = barH(c.composite_score);
          const y = barY(c.composite_score);
          const isSelected = selected?.paper_id === c.paper_id;
          return (
            <g
              key={c.paper_id}
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(isSelected ? null : c)}
            >
              <rect
                x={x}
                y={y}
                width={BAR_W}
                height={h}
                rx={3}
                fill={isSelected ? "hsl(220 70% 50%)" : "hsl(220 70% 72%)"}
                stroke={isSelected ? "hsl(220 70% 35%)" : "none"}
                strokeWidth={1.5}
              />
              {/* Score label above bar (only if bar is tall enough) */}
              {h > 14 && (
                <text
                  x={x + BAR_W / 2}
                  y={y - 3}
                  textAnchor="middle"
                  dominantBaseline="auto"
                  fontSize={7}
                  fill="hsl(220 14% 40%)"
                >
                  {c.composite_score.toFixed(2)}
                </text>
              )}
              {/* Rank label below bar */}
              <text
                x={x + BAR_W / 2}
                y={PAD_T + CHART_H + 6}
                textAnchor="middle"
                dominantBaseline="hanging"
                fontSize={8}
                fontWeight={isSelected ? 600 : 400}
                fill={isSelected ? "hsl(220 70% 35%)" : "hsl(220 14% 45%)"}
              >
                P{i + 1}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function BreakthroughView() {
  const [field, setField] = useState("");
  const [yearRange, setYearRange] = useState<number[]>([2018, 2024]);
  const [topK, setTopK] = useState(10);
  const [showDesc, setShowDesc] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BreakthroughResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BreakthroughCandidate | null>(null);

  function toggleDesc(key: string) {
    setShowDesc((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!field.trim()) return;
    if (yearRange[0] > yearRange[1]) {
      setError("Start year must be ≤ end year.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setSelected(null);
    try {
      const data = await detectBreakthroughs({
        field: field.trim(),
        start_year: yearRange[0],
        end_year: yearRange[1],
        top_k: topK,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Detection failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr] lg:items-start">
      {/* ── Query Form ── */}
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ZapIcon className="size-4" />
              Breakthrough Detection
            </CardTitle>
            <CardDescription>
              Kleinberg burst 분석과 중심성 이동으로 구조적 전환점 논문을 탐지합니다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              {/* Research field */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="field">Research Field</Label>
                  <button
                    type="button"
                    onClick={() => toggleDesc("field")}
                    className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Help{" "}
                    <ChevronDownIcon
                      className={[
                        "size-3 transition-transform",
                        showDesc["field"] ? "rotate-180" : "",
                      ].join(" ")}
                    />
                  </button>
                </div>
                {showDesc["field"] && (
                  <p className="text-xs text-muted-foreground">
                    A research field or method keyword. Papers matching this field will be
                    analyzed for citation burst and centrality shift.
                  </p>
                )}
                <Input
                  id="field"
                  placeholder="e.g. transformer, diffusion models, graph neural networks"
                  value={field}
                  onChange={(e) => setField(e.target.value)}
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
                    Restrict burst detection to papers published within this year range.
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

              {/* Top K */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Label>Top K</Label>
                    <button
                      type="button"
                      onClick={() => toggleDesc("topK")}
                      className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Help{" "}
                      <ChevronDownIcon
                        className={[
                          "size-3 transition-transform",
                          showDesc["topK"] ? "rotate-180" : "",
                        ].join(" ")}
                      />
                    </button>
                  </div>
                  <span className="text-sm font-medium tabular-nums">{topK}</span>
                </div>
                {showDesc["topK"] && (
                  <p className="text-xs text-muted-foreground">
                    Number of top breakthrough candidates to return.
                  </p>
                )}
                <Slider
                  min={5}
                  max={20}
                  step={1}
                  value={[topK]}
                  onValueChange={(val) => {
                    const v = Array.isArray(val) ? val : [val];
                    setTopK(v[0]);
                  }}
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>5</span>
                  <span>20</span>
                </div>
              </div>

              <Button type="submit" disabled={loading || !field.trim()}>
                <ZapIcon />
                {loading ? "Detecting…" : "Detect"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
      </div>

      {/* ── Results ── */}
      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border bg-muted/40 py-24 text-muted-foreground">
          <p className="text-sm">Detecting breakthroughs…</p>
        </div>
      )}

      {!loading && !result && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border bg-muted/40 py-24 text-muted-foreground">
          <ZapIcon className="size-8 opacity-40" />
          <p className="text-sm">Enter a research field and run detection.</p>
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-6">
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{result.total}</span> breakthrough
            candidates detected
          </p>

          {/* Bar chart */}
          <Card>
            <CardHeader>
              <CardTitle>Composite Score — Top {result.candidates.length}</CardTitle>
              <CardDescription>Click a bar to select a candidate</CardDescription>
            </CardHeader>
            <CardContent>
              <BreakthroughBarChart
                candidates={result.candidates}
                selected={selected}
                onSelect={setSelected}
              />
            </CardContent>
          </Card>

          {/* Selected candidate detail */}
          {selected && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ZapIcon className="size-4 text-amber-500" />
                  {selected.title}
                </CardTitle>
                {selected.year && (
                  <CardDescription>{selected.year}</CardDescription>
                )}
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4">
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-muted-foreground">Burst Score</p>
                    <p className="font-mono text-xl font-semibold">
                      {selected.burst_score.toFixed(4)}
                    </p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-muted-foreground">Centrality Shift</p>
                    <p className="font-mono text-xl font-semibold">
                      {selected.centrality_shift.toFixed(4)}
                    </p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-muted-foreground">Composite Score</p>
                    <p className="font-mono text-xl font-semibold text-blue-600 dark:text-blue-400">
                      {selected.composite_score.toFixed(4)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Candidates table */}
          <Card>
            <CardHeader>
              <CardTitle>All Candidates</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-2">
                {result.candidates.map((c, idx) => {
                  const isSelected = selected?.paper_id === c.paper_id;
                  return (
                    <button
                      key={c.paper_id}
                      type="button"
                      onClick={() => setSelected(isSelected ? null : c)}
                      className={[
                        "flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                        isSelected
                          ? "border-ring bg-accent text-accent-foreground"
                          : "border-border hover:bg-muted",
                      ].join(" ")}
                    >
                      <span className="mt-0.5 shrink-0 w-5 text-right text-xs font-mono text-muted-foreground">
                        {idx + 1}
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <p className="text-sm font-medium leading-snug line-clamp-2">
                          {c.title}
                        </p>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                          {c.year && <span>{c.year}</span>}
                          <span>burst {c.burst_score.toFixed(3)}</span>
                          <span>Δcentrality {c.centrality_shift.toFixed(3)}</span>
                        </div>
                      </div>
                      <Badge variant="secondary" className="shrink-0 font-mono">
                        {c.composite_score.toFixed(3)}
                      </Badge>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
