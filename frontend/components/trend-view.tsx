"use client";

import { useState } from "react";
import { ChevronDownIcon, TrendingUpIcon } from "lucide-react";

import { discoverTrending, type TrendMethodResult, type TrendResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";

const YEAR_MIN = 2011;
const YEAR_MAX = 2025;

// ---------------------------------------------------------------------------
// Momentum bar chart (SVG, top-N methods)
// ---------------------------------------------------------------------------

interface MomentumBarChartProps {
  methods: TrendMethodResult[];
}

function MomentumBarChart({ methods }: MomentumBarChartProps) {
  const visible = methods.slice(0, 20);
  if (visible.length === 0) return null;

  const BAR_H = 20;
  const BAR_GAP = 4;
  const PAD_L = 130;
  const PAD_R = 50;
  const PAD_T = 8;
  const CHART_W = 300;

  const maxScore = Math.max(...visible.map((m) => m.momentum_score), 0.001);
  const svgH = PAD_T * 2 + visible.length * (BAR_H + BAR_GAP) - BAR_GAP;
  const svgW = PAD_L + CHART_W + PAD_R;

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} style={{ display: "block" }}>
        {visible.map((m, i) => {
          const y = PAD_T + i * (BAR_H + BAR_GAP);
          const barW = (m.momentum_score / maxScore) * CHART_W;
          return (
            <g key={m.method_name}>
              {/* Method name label */}
              <text
                x={PAD_L - 6}
                y={y + BAR_H / 2}
                textAnchor="end"
                dominantBaseline="central"
                fontSize={9}
                fill="hsl(220 14% 35%)"
              >
                {m.method_name.length > 18
                  ? m.method_name.slice(0, 17) + "…"
                  : m.method_name}
              </text>
              {/* Bar */}
              <rect
                x={PAD_L}
                y={y}
                width={barW}
                height={BAR_H}
                rx={3}
                fill="hsl(220 70% 65%)"
              />
              {/* Score label */}
              <text
                x={PAD_L + barW + 4}
                y={y + BAR_H / 2}
                dominantBaseline="central"
                fontSize={8}
                fill="hsl(220 14% 45%)"
              >
                {m.momentum_score.toFixed(3)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results table
// ---------------------------------------------------------------------------

interface MethodTableProps {
  methods: TrendMethodResult[];
}

function MethodTable({ methods }: MethodTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-1.5 pr-3 font-medium">#</th>
            <th className="py-1.5 pr-3 font-medium">Method</th>
            <th className="py-1.5 pr-3 font-medium text-right">CAGR</th>
            <th className="py-1.5 pr-3 font-medium text-right">Entropy</th>
            <th className="py-1.5 pr-3 font-medium text-right">Velocity</th>
            <th className="py-1.5 font-medium text-right">Score</th>
          </tr>
        </thead>
        <tbody>
          {methods.map((m, idx) => (
            <tr key={m.method_name} className="border-b last:border-0 hover:bg-muted/40">
              <td className="py-1.5 pr-3 font-mono text-muted-foreground">{idx + 1}</td>
              <td className="py-1.5 pr-3 font-medium">{m.method_name}</td>
              <td className="py-1.5 pr-3 text-right font-mono">
                {(m.cagr * 100).toFixed(1)}%
              </td>
              <td className="py-1.5 pr-3 text-right font-mono">{m.entropy.toFixed(3)}</td>
              <td className="py-1.5 pr-3 text-right font-mono">
                {m.adoption_velocity.toFixed(3)}
              </td>
              <td className="py-1.5 text-right font-mono font-semibold">
                {m.momentum_score.toFixed(3)}
              </td>
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

export function TrendView() {
  const [yearRange, setYearRange] = useState<number[]>([2019, 2024]);
  const [topK, setTopK] = useState(20);
  const [showDesc, setShowDesc] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TrendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleDesc(key: string) {
    setShowDesc((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (yearRange[0] > yearRange[1]) {
      setError("Start year must be ≤ end year.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await discoverTrending({
        start_year: yearRange[0],
        end_year: yearRange[1],
        top_k: topK,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery failed");
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
            <TrendingUpIcon className="size-4" />
            Trending Methods Discovery
          </CardTitle>
          <CardDescription>
            Discover which AI methods gained the most momentum in a given period,
            ranked by CAGR, venue diversity, and adoption velocity.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
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
                  Analyze method adoption trends within this publication year range.
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
                  Number of top trending methods to return.
                </p>
              )}
              <Slider
                min={5}
                max={50}
                step={5}
                value={[topK]}
                onValueChange={(val) => {
                  const v = Array.isArray(val) ? val : [val];
                  setTopK(v[0]);
                }}
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>5</span>
                <span>50</span>
              </div>
            </div>

            <Button type="submit" disabled={loading}>
              <TrendingUpIcon />
              {loading ? "Discovering…" : "Discover"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center rounded-xl border bg-muted/40 py-16 text-sm text-muted-foreground">
          Scoring all methods — this may take a moment…
        </div>
      )}

      {!loading && !result && !error && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border bg-muted/40 py-16 text-muted-foreground">
          <TrendingUpIcon className="size-8 opacity-40" />
          <p className="text-sm">Select a year range and run discovery.</p>
        </div>
      )}

      {result && (
        <>
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{result.methods.length}</span> trending
            methods in {result.start_year}–{result.end_year}
          </p>

          {/* Bar chart */}
          <Card>
            <CardHeader>
              <CardTitle>Momentum Score — Top {Math.min(result.methods.length, 20)}</CardTitle>
            </CardHeader>
            <CardContent>
              <MomentumBarChart methods={result.methods} />
            </CardContent>
          </Card>

          {/* Full table */}
          <Card>
            <CardHeader>
              <CardTitle>All Results</CardTitle>
            </CardHeader>
            <CardContent>
              <MethodTable methods={result.methods} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
