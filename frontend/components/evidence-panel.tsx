"use client";

import { ExternalLinkIcon, FileTextIcon, ZapIcon } from "lucide-react";

import { type PaperNode } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SEMANTIC_SCHOLAR_BASE = "https://www.semanticscholar.org/paper/";

// ---------------------------------------------------------------------------
// Score bar — mini horizontal bar for a 0–1 value
// ---------------------------------------------------------------------------

interface ScoreBarProps {
  label: string;
  value: number | null;
  color: string;
}

function ScoreBar({ label, value, color }: ScoreBarProps) {
  const pct = value !== null && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) * 100 : 0;
  const display = value !== null && Number.isFinite(value) ? value.toFixed(4) : "—";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium tabular-nums">{display}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BreakthroughInfo {
  paper_id: string;
  title: string;
  year: number | null;
  burst_score: number;
  centrality_shift: number;
  composite_score: number;
}

interface EvidencePanelProps {
  paper: PaperNode | null;
  /** Populated when the selected paper is a breakthrough candidate. */
  breakthroughInfo?: BreakthroughInfo | null;
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function EvidencePanel({ paper, breakthroughInfo }: EvidencePanelProps) {
  // Determine what to show: prefer PaperNode data, fall back to breakthroughInfo.
  const hasAny = paper !== null || breakthroughInfo !== null;
  const displayId = paper?.paper_id ?? breakthroughInfo?.paper_id ?? null;
  const displayTitle = paper?.title ?? breakthroughInfo?.title ?? null;
  const displayYear = paper?.year ?? breakthroughInfo?.year ?? null;

  if (!hasAny) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Evidence</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center text-muted-foreground">
          <FileTextIcon className="size-8 opacity-30" />
          <p className="text-sm">Select a paper to view score details.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Evidence</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {/* Paper header */}
        <div className="flex flex-col gap-2">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium leading-snug">{displayTitle}</p>
            {displayId && (
              <a
                href={`${SEMANTIC_SCHOLAR_BASE}${displayId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Open in Semantic Scholar"
              >
                <ExternalLinkIcon className="size-4" />
              </a>
            )}
          </div>
          {paper && (
            <p className="text-xs text-muted-foreground">
              {paper.authors.slice(0, 3).join(", ")}
              {paper.authors.length > 3 ? " et al." : ""}
              {displayYear ? ` · ${displayYear}` : ""}
              {` · ${paper.citation_count.toLocaleString()} citations`}
            </p>
          )}
          {!paper && displayYear && (
            <p className="text-xs text-muted-foreground">{displayYear}</p>
          )}
        </div>

        {/* Hybrid score breakdown (lineage papers only) */}
        {paper?.score !== null && paper?.score !== undefined && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">Hybrid Score</span>
              <span className="font-mono font-semibold tabular-nums text-blue-600 dark:text-blue-400">
                {paper.score.toFixed(4)}
              </span>
            </div>
            {(paper.semantic_similarity !== null || paper.graph_proximity !== null) && (
              <div className="flex flex-col gap-2.5 rounded-lg border bg-muted/30 p-3">
                <p className="text-xs font-medium text-muted-foreground">Score Breakdown</p>
                <ScoreBar
                  label="Semantic Similarity"
                  value={paper.semantic_similarity}
                  color="hsl(220 70% 60%)"
                />
                <ScoreBar
                  label="Graph Proximity"
                  value={paper.graph_proximity}
                  color="hsl(142 60% 50%)"
                />
              </div>
            )}
          </div>
        )}

        {/* Breakthrough scores */}
        {breakthroughInfo && (
          <div className="flex flex-col gap-2.5 rounded-lg border bg-amber-50 dark:bg-amber-950/30 p-3">
            <p className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
              <ZapIcon className="size-3" />
              Breakthrough Evidence
            </p>
            <div className="grid grid-cols-1 gap-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Burst Score</span>
                <span className="font-mono font-medium tabular-nums">
                  {breakthroughInfo.burst_score.toFixed(4)}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Centrality Shift</span>
                <span className="font-mono font-medium tabular-nums">
                  {breakthroughInfo.centrality_shift.toFixed(4)}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs border-t pt-2 mt-1">
                <span className="font-medium">Composite Score</span>
                <span className="font-mono font-semibold tabular-nums text-amber-600 dark:text-amber-400">
                  {breakthroughInfo.composite_score.toFixed(4)}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Semantic Scholar ID */}
        {displayId && (
          <div className="flex flex-col gap-1">
            <p className="text-xs text-muted-foreground">Semantic Scholar ID</p>
            <p className="truncate font-mono text-xs text-foreground/70">{displayId}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
