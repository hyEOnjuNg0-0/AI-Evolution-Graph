"use client";

import { useState } from "react";
import { ChevronDownIcon, TrendingUpIcon } from "lucide-react";

import { analyzeTrend, type TrendResponse } from "@/lib/api";
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
// Score breakdown card
// ---------------------------------------------------------------------------

interface ScoreCardProps {
  label: string;
  value: number;
  /** "percent" multiplies by 100 and appends %; "decimal" shows raw value */
  format: "decimal" | "percent";
  description: string;
  highlight?: boolean;
}

function ScoreCard({ label, value, format, description, highlight }: ScoreCardProps) {
  const display = !Number.isFinite(value)
    ? "—"
    : format === "percent"
      ? `${(value * 100).toFixed(1)}%`
      : value.toFixed(4);

  return (
    <div
      className={[
        "flex flex-col gap-1 rounded-lg border px-3 py-2.5",
        highlight ? "border-ring bg-accent" : "bg-muted/30",
      ].join(" ")}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-mono text-xl font-semibold tabular-nums">{display}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function TrendView() {
  const [topic, setTopic] = useState("");
  const [yearRange, setYearRange] = useState<number[]>([2018, 2024]);
  const [showDesc, setShowDesc] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TrendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleDesc(key: string) {
    setShowDesc((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim()) return;
    if (yearRange[0] > yearRange[1]) {
      setError("Start year must be ≤ end year.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await analyzeTrend({
        topic: topic.trim(),
        start_year: yearRange[0],
        end_year: yearRange[1],
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr] lg:items-start">
      {/* ── Query Form + Score Cards ── */}
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUpIcon className="size-4" />
              Trend Momentum Analysis
            </CardTitle>
            <CardDescription>
              CAGR·Shannon 엔트로피·채택 속도로 AI 방법론의 성장 모멘텀을 정량화합니다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              {/* Topic / method */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="topic">Topic / Method</Label>
                  <button
                    type="button"
                    onClick={() => toggleDesc("topic")}
                    className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Help{" "}
                    <ChevronDownIcon
                      className={[
                        "size-3 transition-transform",
                        showDesc["topic"] ? "rotate-180" : "",
                      ].join(" ")}
                    />
                  </button>
                </div>
                {showDesc["topic"] && (
                  <p className="text-xs text-muted-foreground">
                    A method name or research topic. The system analyzes its year-over-year
                    adoption and computes a composite momentum score.
                  </p>
                )}
                <Input
                  id="topic"
                  placeholder="e.g. attention, LoRA, diffusion"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
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
                    Analyze trend momentum within this publication year range.
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

              <Button type="submit" disabled={loading || !topic.trim()}>
                <TrendingUpIcon />
                {loading ? "Analyzing…" : "Analyze"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Score breakdown cards — shown below the form once results arrive */}
        {result && (
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium">
              Momentum Breakdown —{" "}
              <span className="font-mono text-muted-foreground">{result.topic}</span>
            </p>
            <div className="grid grid-cols-2 gap-3">
              <ScoreCard
                label="CAGR"
                value={result.cagr}
                format="percent"
                description="Compound annual growth rate of method usage"
              />
              <ScoreCard
                label="Entropy"
                value={result.entropy}
                format="decimal"
                description="Shannon entropy of venue distribution"
              />
              <ScoreCard
                label="Adoption Velocity"
                value={result.adoption_velocity}
                format="decimal"
                description="Speed of adoption across new papers"
              />
              <ScoreCard
                label="Momentum Score"
                value={result.momentum_score}
                format="decimal"
                description="Composite momentum score"
                highlight
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Graph View (Evolution Path) ── */}
      {/* trendResult is passed so GraphViewPanel defaults to the Evolution Path tab */}
      <GraphViewPanel lineageResult={null} trendResult={result} />
    </div>
  );
}
