"use client";

import { useState } from "react";

import { type LineageResponse, type PaperNode } from "@/lib/api";
import { GraphViewPanel } from "@/components/graph-view-panel";
import { LineageQueryPanel } from "@/components/lineage-query-panel";
import { EvidencePanel } from "@/components/evidence-panel";

/**
 * Client-side shell that owns shared state flowing between panels.
 * Kept separate from page.tsx so the page itself remains a Server Component.
 *
 * Layout (Step 6.5): 3-panel
 *   Left  — LineageQueryPanel (query form + results list)
 *   Center — GraphViewPanel (citation graph / evolution path)
 *   Right  — EvidencePanel (score breakdown for selected paper)
 *
 * Selected paper is lifted here so all three panels stay in sync:
 *   - Clicking a node in the graph sets selectedPaper
 *   - Clicking a paper in the results list also sets selectedPaper
 *   - EvidencePanel reads selectedPaper to display score evidence
 */
export function MainView() {
  const [lineageResult, setLineageResult] = useState<LineageResponse | null>(null);
  const [selectedPaper, setSelectedPaper] = useState<PaperNode | null>(null);

  // Clear selection when a new query result arrives.
  function handleLineageResult(result: LineageResponse) {
    setLineageResult(result);
    setSelectedPaper(null);
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr_280px] lg:items-start">
      <LineageQueryPanel
        onResult={handleLineageResult}
        onSelectPaper={setSelectedPaper}
        selectedPaperId={selectedPaper?.paper_id ?? null}
      />
      <GraphViewPanel
        lineageResult={lineageResult}
        selectedPaperId={selectedPaper?.paper_id ?? null}
        onSelectPaper={setSelectedPaper}
      />
      <EvidencePanel paper={selectedPaper} />
    </div>
  );
}
