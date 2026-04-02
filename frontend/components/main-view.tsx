"use client";

import { useState } from "react";

import { type BreakthroughResponse, type LineageResponse, type TrendResponse } from "@/lib/api";
import { GraphViewPanel } from "@/components/graph-view-panel";
import { LineageQueryPanel } from "@/components/lineage-query-panel";

/**
 * Client-side shell that owns shared state flowing between panels.
 * Kept separate from page.tsx so the page itself remains a Server Component.
 */
export function MainView() {
  const [lineageResult, setLineageResult] = useState<LineageResponse | null>(null);
  // trendResult and breakthroughResult will be populated by the Insight Panel in Step 6.4
  const [trendResult] = useState<TrendResponse | null>(null);
  const [breakthroughResult] = useState<BreakthroughResponse | null>(null);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr] lg:items-start">
      <LineageQueryPanel onResult={setLineageResult} />
      <GraphViewPanel
        lineageResult={lineageResult}
        trendResult={trendResult}
        breakthroughResult={breakthroughResult}
      />
    </div>
  );
}
