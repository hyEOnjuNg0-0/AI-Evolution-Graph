"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLinkIcon } from "lucide-react";

import {
  type CitationEdge,
  type LineageResponse,
  type PaperNode,
  type TrendResponse,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// ---------------------------------------------------------------------------
// Force-directed layout (Fruchterman-Reingold, runs synchronously)
// Suitable for n ≤ 20; O(n²) per iteration × 120 iters.
// ---------------------------------------------------------------------------

type Vec2 = { x: number; y: number };

function computeForceLayout(
  nodeIds: string[],
  edges: { src: string; tgt: string }[],
  w: number,
  h: number
): Map<string, Vec2> {
  const n = nodeIds.length;
  if (n === 0) return new Map();
  if (n === 1) return new Map([[nodeIds[0], { x: w / 2, y: h / 2 }]]);

  // Initialise in a circle so the layout is deterministic
  const pos = new Map<string, Vec2>(
    nodeIds.map((id, i) => {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      const r = Math.min(w, h) * 0.38;
      return [id, { x: w / 2 + r * Math.cos(angle), y: h / 2 + r * Math.sin(angle) }];
    })
  );

  const k = Math.sqrt((w * h) / n) * 0.75;
  const pad = 50;

  for (let iter = 0; iter < 120; iter++) {
    const disp = new Map<string, Vec2>(nodeIds.map((id) => [id, { x: 0, y: 0 }]));

    // Coulomb repulsion between every pair
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = pos.get(nodeIds[i])!;
        const b = pos.get(nodeIds[j])!;
        const dx = a.x - b.x || 0.01;
        const dy = a.y - b.y || 0.01;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (k * k) / dist;
        const di = disp.get(nodeIds[i])!;
        const dj = disp.get(nodeIds[j])!;
        di.x += (dx / dist) * f;
        di.y += (dy / dist) * f;
        dj.x -= (dx / dist) * f;
        dj.y -= (dy / dist) * f;
      }
    }

    // Hooke attraction along edges
    for (const { src, tgt } of edges) {
      const a = pos.get(src);
      const b = pos.get(tgt);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (dist * dist) / k;
      const ds = disp.get(src)!;
      const dt = disp.get(tgt)!;
      ds.x += (dx / dist) * f;
      ds.y += (dy / dist) * f;
      dt.x -= (dx / dist) * f;
      dt.y -= (dy / dist) * f;
    }

    // Apply displacement with simulated-annealing temperature cooling
    const temp = Math.max(4, 70 * (1 - iter / 120));
    for (const id of nodeIds) {
      const d = disp.get(id)!;
      const p = pos.get(id)!;
      const mag = Math.sqrt(d.x * d.x + d.y * d.y) || 0.01;
      const scale = Math.min(mag, temp) / mag;
      p.x = Math.max(pad, Math.min(w - pad, p.x + d.x * scale));
      p.y = Math.max(pad, Math.min(h - pad, p.y + d.y * scale));
    }
  }

  return pos;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SVG_W = 700;
const SVG_H = 420;
const NODE_R = 22;
const SEMANTIC_SCHOLAR_BASE = "https://www.semanticscholar.org/paper/";

/** Map a hybrid score [0, 1] to an HSL fill colour. */
function scoreToFill(score: number | null): string {
  if (score === null) return "hsl(220 14% 55%)";
  const lightness = Math.round(70 - score * 30); // 70 → 40 as score rises
  return `hsl(220 70% ${lightness}%)`;
}

// ---------------------------------------------------------------------------
// Citation Graph
// ---------------------------------------------------------------------------

interface CitationGraphViewProps {
  papers: PaperNode[];
  edges: CitationEdge[];
}

function CitationGraphView({ papers, edges }: CitationGraphViewProps) {
  const years = papers.map((p) => p.year).filter((y): y is number => y !== null);
  const minYear = years.length ? Math.min(...years) : 2011;
  const maxYear = years.length ? Math.max(...years) : 2025;
  const hasRange = minYear < maxYear;

  const [yearRange, setYearRange] = useState<[number, number]>([minYear, maxYear]);
  const [selected, setSelected] = useState<PaperNode | null>(null);

  // Clear selection when it falls outside the current year filter
  useEffect(() => {
    if (
      selected?.year !== undefined &&
      selected.year !== null &&
      (selected.year < yearRange[0] || selected.year > yearRange[1])
    ) {
      setSelected(null);
    }
  }, [yearRange, selected]);

  const visiblePapers = useMemo(
    () =>
      papers.filter(
        (p) => p.year === null || (p.year >= yearRange[0] && p.year <= yearRange[1])
      ),
    [papers, yearRange]
  );

  const visibleIds = useMemo(
    () => new Set(visiblePapers.map((p) => p.paper_id)),
    [visiblePapers]
  );

  const visibleEdges = useMemo(
    () => edges.filter((e) => visibleIds.has(e.source_id) && visibleIds.has(e.target_id)),
    [edges, visibleIds]
  );

  const forceEdges = useMemo(
    () => visibleEdges.map((e) => ({ src: e.source_id, tgt: e.target_id })),
    [visibleEdges]
  );

  const layout = useMemo(
    () =>
      computeForceLayout(
        visiblePapers.map((p) => p.paper_id),
        forceEdges,
        SVG_W,
        SVG_H
      ),
    [visiblePapers, forceEdges]
  );

  // Rank label map: sorted by score desc (null scores go last) → P1, P2, …
  // Based on the full papers array so rank numbers stay stable across year filters.
  const rankLabel = useMemo(() => {
    const sorted = [...papers].sort((a, b) => {
      if (a.score === null && b.score === null) return 0;
      if (a.score === null) return 1;
      if (b.score === null) return -1;
      return b.score - a.score;
    });
    return new Map(sorted.map((p, i) => [p.paper_id, `P${i + 1}`]));
  }, [papers]);

  return (
    <div className="flex flex-col gap-4">
      {/* Year filter slider */}
      {hasRange && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Year filter</span>
            <span className="font-medium tabular-nums">
              {yearRange[0]} – {yearRange[1]}
            </span>
          </div>
          <Slider
            min={minYear}
            max={maxYear}
            step={1}
            value={yearRange}
            onValueChange={(val) => {
              const v = Array.isArray(val) ? [...val] : [val, val];
              if (v.length >= 2 && v[0] <= v[1]) setYearRange([v[0], v[1]]);
            }}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{minYear}</span>
            <span>{maxYear}</span>
          </div>
        </div>
      )}

      {/* SVG graph */}
      <div className="overflow-hidden rounded-lg border bg-background">
        <svg
          width="100%"
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          className="block"
          style={{ minHeight: 280 }}
        >
          <defs>
            <marker
              id="cg-arrow"
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 8 3, 0 6" fill="hsl(220 14% 60%)" />
            </marker>
          </defs>

          {/* Edges */}
          {visibleEdges.map((e, i) => {
            const a = layout.get(e.source_id);
            const b = layout.get(e.target_id);
            if (!a || !b) return null;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            // Stop line at node boundary to avoid overlapping the arrowhead
            const x1 = a.x + (dx / dist) * NODE_R;
            const y1 = a.y + (dy / dist) * NODE_R;
            const x2 = b.x - (dx / dist) * (NODE_R + 5);
            const y2 = b.y - (dy / dist) * (NODE_R + 5);
            return (
              <line
                key={i}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="hsl(220 14% 75%)"
                strokeWidth={1.2}
                markerEnd="url(#cg-arrow)"
              />
            );
          })}

          {/* Nodes */}
          {visiblePapers.map((paper) => {
            const pos = layout.get(paper.paper_id);
            if (!pos) return null;
            const isSelected = selected?.paper_id === paper.paper_id;
            return (
              <g
                key={paper.paper_id}
                transform={`translate(${pos.x},${pos.y})`}
                style={{ cursor: "pointer" }}
                onClick={() => setSelected(isSelected ? null : paper)}
              >
                <circle
                  r={NODE_R}
                  fill={scoreToFill(paper.score)}
                  stroke={isSelected ? "hsl(0 72% 51%)" : "hsl(220 14% 85%)"}
                  strokeWidth={isSelected ? 2.5 : 1.5}
                />
                {/* Rank label inside node (P1 = highest score) */}
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={9}
                  fontWeight={600}
                  fill="white"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {rankLabel.get(paper.paper_id)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Selected paper detail panel */}
      {selected && (
        <div className="rounded-lg border bg-card px-4 py-3 text-sm ring-1 ring-foreground/10">
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium leading-snug">{selected.title}</p>
            <a
              href={`${SEMANTIC_SCHOLAR_BASE}${selected.paper_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Open in Semantic Scholar"
            >
              <ExternalLinkIcon className="size-4" />
            </a>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {selected.authors.slice(0, 3).join(", ")}
            {selected.authors.length > 3 ? " et al." : ""}
            {selected.year ? ` · ${selected.year}` : ""}
            {` · ${selected.citation_count.toLocaleString()} citations`}
          </p>
          {selected.score !== null && (
            <p className="mt-1 text-xs">
              <span className="text-muted-foreground">Hybrid score: </span>
              <span className="font-mono font-medium">{selected.score.toFixed(4)}</span>
            </p>
          )}
        </div>
      )}

      <p className="text-center text-xs text-muted-foreground">
        {visiblePapers.length} nodes · {visibleEdges.length} edges · click a node for details
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evolution Path (horizontal DAG)
// ---------------------------------------------------------------------------

const BREAKTHROUGH_THRESHOLD = 0.5;

interface EvolutionPathViewProps {
  evolutionPath: TrendResponse["evolution_path"];
  /** Optional map of method name → composite_score for breakthrough badge */
  breakthroughScores?: Map<string, number>;
}

function EvolutionPathView({ evolutionPath, breakthroughScores }: EvolutionPathViewProps) {
  if (evolutionPath.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
        No evolution path data available.
      </div>
    );
  }

  // Collect unique method names preserving order of first appearance
  const methodNames: string[] = [];
  const seen = new Set<string>();
  for (const step of evolutionPath) {
    if (!seen.has(step.from_method)) {
      methodNames.push(step.from_method);
      seen.add(step.from_method);
    }
    if (!seen.has(step.to_method)) {
      methodNames.push(step.to_method);
      seen.add(step.to_method);
    }
  }

  const BOX_W = 120;
  const BOX_H = 44;
  const GAP_X = 80;
  const PAD_X = 20;
  const PAD_Y = 24;
  const svgW = PAD_X * 2 + methodNames.length * BOX_W + (methodNames.length - 1) * GAP_X;
  const svgH = BOX_H + PAD_Y * 2 + 20; // extra vertical room for edge labels

  const boxLeft = (i: number) => PAD_X + i * (BOX_W + GAP_X);
  const centerY = PAD_Y + BOX_H / 2;

  return (
    <div className="overflow-x-auto rounded-lg border bg-background p-4">
      <svg width={svgW} height={svgH} style={{ display: "block" }}>
        <defs>
          <marker
            id="evo-arrow"
            markerWidth="8"
            markerHeight="6"
            refX="8"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="hsl(220 14% 60%)" />
          </marker>
        </defs>

        {/* Edges with relation_type labels */}
        {evolutionPath.map((step, i) => {
          const fromIdx = methodNames.indexOf(step.from_method);
          const toIdx = methodNames.indexOf(step.to_method);
          if (fromIdx < 0 || toIdx < 0) return null;
          const x1 = boxLeft(fromIdx) + BOX_W;
          const x2 = boxLeft(toIdx) - 5;
          const labelX = (x1 + x2) / 2;
          return (
            <g key={i}>
              <line
                x1={x1}
                y1={centerY}
                x2={x2}
                y2={centerY}
                stroke="hsl(220 14% 65%)"
                strokeWidth={1.5}
                markerEnd="url(#evo-arrow)"
              />
              {/* Relation type label above the edge */}
              <text
                x={labelX}
                y={centerY - 7}
                textAnchor="middle"
                fontSize={9}
                fill="hsl(220 14% 45%)"
              >
                {step.relation_type}
              </text>
              {/* Year label below the edge */}
              {step.year !== null && (
                <text
                  x={labelX}
                  y={centerY + 16}
                  textAnchor="middle"
                  fontSize={8}
                  fill="hsl(220 14% 60%)"
                >
                  {step.year}
                </text>
              )}
            </g>
          );
        })}

        {/* Method nodes */}
        {methodNames.map((name, i) => {
          const x = boxLeft(i);
          const score = breakthroughScores?.get(name);
          const isBreakthrough = score !== undefined && score >= BREAKTHROUGH_THRESHOLD;
          return (
            <g key={name}>
              <rect
                x={x}
                y={PAD_Y}
                width={BOX_W}
                height={BOX_H}
                rx={6}
                fill={isBreakthrough ? "hsl(43 96% 90%)" : "hsl(220 14% 95%)"}
                stroke={isBreakthrough ? "hsl(43 96% 50%)" : "hsl(220 14% 80%)"}
                strokeWidth={1.5}
              />
              {/* Method name via foreignObject for automatic text wrapping */}
              <foreignObject x={x + 4} y={PAD_Y + 4} width={BOX_W - 8} height={BOX_H - 8}>
                <div
                  style={{
                    fontSize: 9,
                    lineHeight: 1.3,
                    wordBreak: "break-word",
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    textAlign: "center",
                  }}
                >
                  {name}
                </div>
              </foreignObject>
              {/* Breakthrough star badge */}
              {isBreakthrough && (
                <text
                  x={x + BOX_W - 4}
                  y={PAD_Y + 2}
                  textAnchor="end"
                  dominantBaseline="hanging"
                  fontSize={9}
                  fill="hsl(43 96% 40%)"
                >
                  ★
                </text>
              )}
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

export interface GraphViewPanelProps {
  lineageResult: LineageResponse | null;
  trendResult: TrendResponse | null;
}

export function GraphViewPanel({ lineageResult, trendResult }: GraphViewPanelProps) {
  if (!lineageResult && !trendResult) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16 text-sm text-muted-foreground">
          Run a query to visualise the citation graph.
        </CardContent>
      </Card>
    );
  }

  const defaultTab = lineageResult ? "citation" : "evolution";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Graph View</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={defaultTab}>
          <TabsList>
            <TabsTrigger value="citation" disabled={!lineageResult}>
              Citation Graph
            </TabsTrigger>
            <TabsTrigger value="evolution" disabled={!trendResult}>
              Evolution Path
            </TabsTrigger>
          </TabsList>

          <TabsContent value="citation" className="mt-4">
            {lineageResult && (
              // Key resets internal state (year range, selection) when the query result changes
              <CitationGraphView
                key={lineageResult.papers[0]?.paper_id ?? "empty"}
                papers={lineageResult.papers}
                edges={lineageResult.edges}
              />
            )}
          </TabsContent>

          <TabsContent value="evolution" className="mt-4">
            {trendResult ? (
              <EvolutionPathView evolutionPath={trendResult.evolution_path} />
            ) : (
              <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
                Run a Trend Momentum analysis to view the evolution path.
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
