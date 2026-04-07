"use client";

import { useEffect, useMemo, useState } from "react";

import {
  type CitationEdge,
  type EvolutionResponse,
  type EvolutionStep,
  type LineageResponse,
  type PaperNode,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";

// ---------------------------------------------------------------------------
// Force-directed layout (Fruchterman-Reingold, runs synchronously)
// Suitable for n ≤ 100; iterations scale as ⌊6000/n⌋ to keep O(n² × iter) bounded.
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

  // Scale iteration count with n: large graphs get fewer iterations to avoid blocking the main thread
  const iterations = Math.max(30, Math.min(120, Math.floor(6000 / n)));
  for (let iter = 0; iter < iterations; iter++) {
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
    const temp = Math.max(4, 70 * (1 - iter / iterations));
    for (const id of nodeIds) {
      const d = disp.get(id)!;
      const p = pos.get(id)!;
      const mag = Math.sqrt(d.x * d.x + d.y * d.y);
      // Guard: skip zero/Infinity/NaN displacement — Infinity*0 = NaN would corrupt positions
      if (!isFinite(mag) || mag === 0) continue;
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
// Above this node count, force-layout iterations are reduced; a warning is shown in the UI.
const FORCE_LAYOUT_WARN_THRESHOLD = 25;

/** Map a hybrid score [0, 1] to an HSL fill colour. */
function scoreToFill(score: number | null): string {
  if (score === null || !isFinite(score)) return "hsl(220 14% 55%)";
  // Clamp to [0, 100] so out-of-range scores don't produce invalid CSS (e.g. hsl(220 70% -80%))
  const lightness = Math.max(0, Math.min(100, Math.round(70 - score * 30))); // 70 → 40 as score rises
  return `hsl(220 70% ${lightness}%)`;
}

// ---------------------------------------------------------------------------
// Citation Graph
// ---------------------------------------------------------------------------

interface CitationGraphViewProps {
  papers: PaperNode[];
  edges: CitationEdge[];
  selectedPaperId: string | null;
  onSelectPaper: (paper: PaperNode | null) => void;
  /** Paper IDs to mark with an amber border (e.g. breakthrough candidates). */
  highlightedPaperIds?: Set<string>;
}

function CitationGraphView({ papers, edges, selectedPaperId, onSelectPaper, highlightedPaperIds }: CitationGraphViewProps) {
  const years = papers.map((p) => p.year).filter((y): y is number => y !== null);
  const minYear = years.length ? Math.min(...years) : 2011;
  const maxYear = years.length ? Math.max(...years) : 2025;
  // Only show the slider when there is a real year range AND at least one paper has a year.
  // If all years are null the slider would render but have no filtering effect.
  const hasRange = years.length > 0 && minYear < maxYear;

  const [yearRange, setYearRange] = useState<[number, number]>([minYear, maxYear]);

  // Reset year range when the data's year bounds change (e.g., query switches from
  // single-year to multi-year results while the first paper ID stays the same)
  useEffect(() => {
    setYearRange([minYear, maxYear]);
  }, [minYear, maxYear]);

  // Warn in development when highlighted IDs don't correspond to any paper in the graph
  useEffect(() => {
    if (process.env.NODE_ENV !== "development" || !highlightedPaperIds) return;
    const paperIds = new Set(papers.map((p) => p.paper_id));
    for (const id of highlightedPaperIds) {
      if (!paperIds.has(id)) {
        console.warn(`[GraphView] highlightedPaperIds contains unknown paper ID: "${id}"`);
      }
    }
  }, [highlightedPaperIds, papers]);

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

  // When the selected paper is filtered out by the year slider, deselect it in the parent.
  useEffect(() => {
    if (selectedPaperId && !visibleIds.has(selectedPaperId)) {
      onSelectPaper(null);
    }
  }, [visibleIds, selectedPaperId, onSelectPaper]);

  const visibleEdges = useMemo(
    () => edges.filter((e) => visibleIds.has(e.source_id) && visibleIds.has(e.target_id)),
    [edges, visibleIds]
  );

  // Count highlighted papers hidden by the year filter so the user knows the highlight hasn't been lost
  const hiddenHighlightCount = useMemo(() => {
    if (!highlightedPaperIds || highlightedPaperIds.size === 0) return 0;
    let count = 0;
    for (const id of highlightedPaperIds) {
      if (!visibleIds.has(id)) count++;
    }
    return count;
  }, [highlightedPaperIds, visibleIds]);

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
              const [lo, hi] = v;
              if (typeof lo === "number" && typeof hi === "number" && lo <= hi) {
                setYearRange([lo, hi]);
              }
            }}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{minYear}</span>
            <span>{maxYear}</span>
          </div>
        </div>
      )}

      {/* Warn when highlighted papers are hidden by the year filter */}
      {hiddenHighlightCount > 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {hiddenHighlightCount} highlighted {hiddenHighlightCount === 1 ? "paper is" : "papers are"} outside the current year range.
        </p>
      )}

      {/* Large-graph performance warning */}
      {visiblePapers.length > FORCE_LAYOUT_WARN_THRESHOLD && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {visiblePapers.length} nodes — layout quality is reduced at this scale. Use the year filter to narrow results.
        </p>
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
            // Guard: skip missing nodes or NaN coordinates (residual from force-layout edge cases)
            if (!a || !b || !isFinite(a.x) || !isFinite(a.y) || !isFinite(b.x) || !isFinite(b.y)) {
              if (process.env.NODE_ENV === "development") {
                console.warn(`[GraphView] Skipping edge ${e.source_id} → ${e.target_id}: missing or non-finite coordinates`);
              }
              return null;
            }
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
            const isSelected = paper.paper_id === selectedPaperId;
            // Breakthrough candidates get amber fill; selected overrides with normal fill + red stroke.
            const isHighlighted = highlightedPaperIds?.has(paper.paper_id) ?? false;
            const fill = isHighlighted && !isSelected
              ? "hsl(43 96% 75%)"
              : scoreToFill(paper.score);
            const stroke = isSelected
              ? "hsl(0 72% 51%)"
              : isHighlighted
                ? "hsl(43 96% 45%)"
                : "hsl(220 14% 85%)";
            const strokeWidth = isSelected || isHighlighted ? 2.5 : 1.5;
            return (
              <g
                key={paper.paper_id}
                transform={`translate(${pos.x},${pos.y})`}
                style={{ cursor: "pointer" }}
                onClick={() => onSelectPaper(isSelected ? null : paper)}
              >
                <circle r={NODE_R} fill={fill} stroke={stroke} strokeWidth={strokeWidth} />
                {/* Rank label inside node (P1 = highest score) */}
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={9}
                  fontWeight={600}
                  fill={isHighlighted && !isSelected ? "hsl(43 96% 20%)" : "white"}
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {rankLabel.get(paper.paper_id)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

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
  evolutionPath: EvolutionStep[];
  /** Optional map of method name → influence score for breakthrough badge */
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
  const ARC_BASE = 40;
  const ARC_STRIDE = 35; // vertical gap between stacked backward arcs

  const boxLeft = (i: number) => PAD_X + i * (BOX_W + GAP_X);
  const centerY = PAD_Y + BOX_H / 2;

  // Detect true back edges (cycle-creating) via DFS.
  // Positional checks (toIdx < fromIdx) alone false-positive on converging DAGs
  // where a non-cyclic edge happens to point leftward in the layout.
  const backEdgeIndices = (() => {
    const WHITE = 0, GRAY = 1, BLACK = 2;
    const color: Record<string, number> = {};
    for (const name of methodNames) color[name] = WHITE;
    const result = new Set<number>();

    // Build per-node outgoing edge list, keyed by source method name
    const outEdges = new Map<string, { to: string; idx: number }[]>();
    for (const name of methodNames) outEdges.set(name, []);
    evolutionPath.forEach((step, idx) => {
      if (step.from_method in color && step.to_method in color) {
        outEdges.get(step.from_method)!.push({ to: step.to_method, idx });
      }
    });

    // Iterative DFS using an explicit stack to avoid call-stack overflow on large graphs.
    // Stack entries: [node, iterator over its outgoing edges]
    for (const start of methodNames) {
      if (color[start] !== WHITE) continue;
      // Each stack frame: [nodeName, edgeIndex into outEdges[node]]
      const stack: [string, number][] = [[start, 0]];
      color[start] = GRAY;
      while (stack.length > 0) {
        const frame = stack[stack.length - 1];
        const [u, ei] = frame;
        const edges = outEdges.get(u) ?? [];
        if (ei >= edges.length) {
          color[u] = BLACK;
          stack.pop();
        } else {
          frame[1]++; // advance edge pointer before potential push
          const { to, idx } = edges[ei];
          if (color[to] === GRAY) {
            result.add(idx); // back edge: target is an ancestor in the DFS tree
          } else if (color[to] === WHITE) {
            color[to] = GRAY;
            stack.push([to, 0]);
          }
        }
      }
    }
    return result;
  })();

  // Pre-compute backward edge arc tiers so each arc sits at a unique depth.
  const backwardTiers = new Map<number, number>();
  let backwardCount = 0;
  evolutionPath.forEach((_step, idx) => {
    if (backEdgeIndices.has(idx)) {
      backwardTiers.set(idx, backwardCount++);
    }
  });
  const maxArcDepth = backwardCount > 0 ? ARC_BASE + (backwardCount - 1) * ARC_STRIDE : ARC_BASE;

  // Pre-compute forward edge label lanes to prevent y-overlap.
  // Two labels collide when their x-midpoints are within LABEL_HALF_W*2 px on the same lane;
  // a colliding label is bumped to lane 1 (shifted further above the line).
  const LABEL_HALF_W = 30;
  const forwardLanes = new Map<number, number>();
  const placedFwdLabels: { x: number; lane: number }[] = [];
  evolutionPath.forEach((step, idx) => {
    if (backEdgeIndices.has(idx)) return; // back edges are arcs, not straight lines
    const fi = methodNames.indexOf(step.from_method);
    const ti = methodNames.indexOf(step.to_method);
    if (fi < 0 || ti < 0 || fi === ti) return;
    const labelX = (boxLeft(fi) + BOX_W + boxLeft(ti) - 5) / 2;
    // Probe lanes 0, 1, 2, … until finding one with no x-overlap (cap at 20 to prevent runaway)
    let lane = 0;
    while (lane < 20 && placedFwdLabels.some((l) => l.lane === lane && Math.abs(l.x - labelX) < LABEL_HALF_W * 2)) {
      lane++;
    }
    forwardLanes.set(idx, lane);
    placedFwdLabels.push({ x: labelX, lane });
  });

  const svgW = PAD_X * 2 + methodNames.length * BOX_W + (methodNames.length - 1) * GAP_X;
  const svgH = BOX_H + PAD_Y * 2 + 20 + maxArcDepth;

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
          if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return null;

          // True back edge (cycle-creating) detected by DFS, not by positional comparison
          const isBackward = backEdgeIndices.has(i);

          if (isBackward) {
            // Each backward arc uses a unique depth tier to avoid overlap.
            const tier = backwardTiers.get(i) ?? 0;
            const cx_from = boxLeft(fromIdx) + BOX_W / 2;
            const cx_to = boxLeft(toIdx) + BOX_W / 2;
            const yBottom = PAD_Y + BOX_H;
            const yArc = yBottom + ARC_BASE + tier * ARC_STRIDE;
            const arrowTipY = yBottom - 2; // just inside box bottom for clean arrowhead placement
            const pathD = `M ${cx_from},${yBottom} C ${cx_from},${yArc} ${cx_to},${yArc} ${cx_to},${arrowTipY}`;
            const labelX = (cx_from + cx_to) / 2;
            const labelY = yArc + 4;
            return (
              <g key={i}>
                <path
                  d={pathD}
                  fill="none"
                  stroke="hsl(220 14% 65%)"
                  strokeWidth={1.5}
                  markerEnd="url(#evo-arrow)"
                />
                <text x={labelX} y={labelY} textAnchor="middle" fontSize={9} fill="hsl(220 14% 45%)">
                  {step.relation_type}
                </text>
                {step.year !== null && (
                  <text x={labelX} y={labelY + 11} textAnchor="middle" fontSize={8} fill="hsl(220 14% 60%)">
                    {step.year}
                  </text>
                )}
              </g>
            );
          }

          // Forward edge: straight horizontal line between adjacent boxes
          const x1 = boxLeft(fromIdx) + BOX_W;
          const x2 = boxLeft(toIdx) - 5;
          const labelX = (x1 + x2) / 2;
          // Lane 0 = just above the line; lane 1 = shifted further up to avoid x-overlap
          const fwdLane = forwardLanes.get(i) ?? 0;
          const fwdLabelY = centerY - 7 - fwdLane * 12;
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
              {/* Relation type label, staggered by lane to prevent overlap */}
              <text
                x={labelX}
                y={fwdLabelY}
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
  evolutionResult?: EvolutionResponse | null;
  selectedPaperId?: string | null;
  onSelectPaper?: (paper: PaperNode | null) => void;
  /** Paper IDs to mark with amber highlighting (e.g. breakthrough candidates). */
  highlightedPaperIds?: Set<string>;
}

export function GraphViewPanel({ lineageResult, evolutionResult, selectedPaperId, onSelectPaper, highlightedPaperIds }: GraphViewPanelProps) {
  if (!lineageResult && !evolutionResult) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16 text-sm text-muted-foreground">
          Run a query to visualise the citation graph.
        </CardContent>
      </Card>
    );
  }

  const subtitle = lineageResult ? "Citation Graph" : "Evolution Path";

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Graph View
          <span className="ml-2 text-sm font-normal text-muted-foreground">— {subtitle}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {lineageResult ? (
          // Key resets internal state (year range) when the query result changes
          <CitationGraphView
            key={lineageResult.papers[0]?.paper_id ?? "empty"}
            papers={lineageResult.papers}
            edges={lineageResult.edges}
            selectedPaperId={selectedPaperId ?? null}
            onSelectPaper={onSelectPaper ?? (() => undefined)}
            highlightedPaperIds={highlightedPaperIds}
          />
        ) : (
          <EvolutionPathView
            evolutionPath={evolutionResult!.evolution_path}
            breakthroughScores={
              Object.keys(evolutionResult!.influence_scores).length > 0
                ? new Map(Object.entries(evolutionResult!.influence_scores))
                : undefined
            }
          />
        )}
      </CardContent>
    </Card>
  );
}
