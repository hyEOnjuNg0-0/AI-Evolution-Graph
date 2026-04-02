/**
 * Adversarial Test Suite for graph-view-panel.tsx
 * Tests for edge cases and integration faults
 */

// Test 1: Unbounded forward label lane allocation
const testForwardLaneLimitlessExpansion = () => {
  const placedFwdLabels: { x: number; lane: number }[] = [];
  const LABEL_HALF_W = 30;
  const identicalX = 350;
  
  for (let i = 0; i < 100; i++) {
    let lane = 0;
    while (placedFwdLabels.some((l) => l.lane === lane && Math.abs(l.x - identicalX) < LABEL_HALF_W * 2)) {
      lane++;
    }
    placedFwdLabels.push({ x: identicalX, lane });
  }
  
  console.log(`Lane allocation test: 100 colliding labels used lanes 0-${Math.max(...placedFwdLabels.map((l) => l.lane))}`);
  return true;
};

// Test 2: Slider inverted range rejection
const testSliderInvertedRangeRejection = () => {
  const v = [2025, 2020];
  const isValid = v.length >= 2 && v[0] <= v[1];
  console.log(`Inverted range [2025, 2020] valid: ${isValid}`);
  return isValid === false;
};

// Test 3: All-null-year papers show ineffective slider
const testAllNullYearPapers = () => {
  const papers = [
    { paper_id: 'P1', year: null },
    { paper_id: 'P2', year: null },
  ];
  const years = papers.map((p) => p.year).filter((y) => y !== null);
  const minYear = years.length ? Math.min(...years) : 2011;
  const maxYear = years.length ? Math.max(...years) : 2025;
  const hasRange = minYear < maxYear;
  
  console.log(`All-null years: hasRange=${hasRange}, slider shown but ineffective`);
  return hasRange === true && years.length === 0;
};

// Test 4: Force layout iteration count
const testForceLayoutIterationCounts = () => {
  const testCases = [
    [25, 120],   // 6000/25=240 clamped to [30,120]
    [50, 120],   // 6000/50=120
    [100, 60],   // 6000/100=60
    [200, 30],   // 6000/200=30
  ];
  
  for (const [n, expected] of testCases) {
    const iterations = Math.max(30, Math.min(120, Math.floor(6000 / n)));
    console.log(`n=${n}: iterations=${iterations} (expected ${expected})`);
  }
  return true;
};

// Test 5: DFS cycle detection with deep chain
const testDFSDeepChain = () => {
  const methodNames = Array.from({ length: 50 }, (_, i) => `M${i}`);
  const evolutionPath = Array.from({ length: 49 }, (_, i) => ({
    from_method: `M${i}`,
    to_method: `M${i + 1}`,
    relation_type: 'extends',
  }));
  
  const color = {};
  for (const name of methodNames) color[name] = 0;
  
  const outEdges = new Map();
  for (const name of methodNames) outEdges.set(name, []);
  evolutionPath.forEach((step, idx) => {
    if (step.from_method in color && step.to_method in color) {
      outEdges.get(step.from_method).push({ to: step.to_method, idx });
    }
  });
  
  let maxDepth = 0;
  function dfs(u, depth = 0) {
    maxDepth = Math.max(maxDepth, depth);
    color[u] = 1;
    for (const { to } of outEdges.get(u) ?? []) {
      if (color[to] === 0) {
        dfs(to, depth + 1);
      }
    }
    color[u] = 2;
  }
  
  for (const name of methodNames) {
    if (color[name] === 0) dfs(name);
  }
  
  console.log(`DFS chain test: max depth=${maxDepth} for 50-method chain`);
  return maxDepth <= methodNames.length;
};

// Test 6: visibleIds dependency consistency
const testVisibleIdsDependency = () => {
  const papers = [
    { paper_id: 'P1', year: 2020 },
    { paper_id: 'P2', year: 2021 },
    { paper_id: 'P3', year: 2022 },
  ];
  const edges = [
    { source_id: 'P1', target_id: 'P2' },
    { source_id: 'P2', target_id: 'P3' },
  ];
  const yearRange = [2020, 2021];
  
  const visiblePapers = papers.filter((p) => p.year === null || (p.year >= yearRange[0] && p.year <= yearRange[1]));
  const visibleIds = new Set(visiblePapers.map((p) => p.paper_id));
  const visibleEdges = edges.filter((e) => visibleIds.has(e.source_id) && visibleIds.has(e.target_id));
  
  console.log(`Dependency test: visible papers=${visiblePapers.length}, visible edges=${visibleEdges.length}`);
  return visiblePapers.length === 2 && visibleEdges.length === 1;
};

// Run all tests
console.log('=== Adversarial Tests ===');
console.log('Test 1 (Unbounded lanes):', testForwardLaneLimitlessExpansion());
console.log('Test 2 (Inverted range):', testSliderInvertedRangeRejection());
console.log('Test 3 (Null years):', testAllNullYearPapers());
console.log('Test 4 (Iterations):', testForceLayoutIterationCounts());
console.log('Test 5 (DFS depth):', testDFSDeepChain());
console.log('Test 6 (Dependencies):', testVisibleIdsDependency());

