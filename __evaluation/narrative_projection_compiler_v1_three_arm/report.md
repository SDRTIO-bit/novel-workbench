======================================================================
NARRATIVE PROJECTION COMPILER v1 — THREE-ARM EXPERIMENT
FINAL REPORT
======================================================================

HEAD: a990542789583602bd0978329dd11a5f7c7a5926
Experiment: NARRATIVE_PROJECTION_COMPILER_V1_THREE_ARM
Date: 2026-07-21/22

── EXECUTION SUMMARY ──
Stage 1 (smoke):  4 scenes × 1 replica  =  4 planners, 12 writers
Stage 2 (formal): 6 scenes × 3 replicas = 18 planners, 54 writers
Total LLM calls:  72 (22 planners + 50 writers that ran)

Planners succeeded: 22/22
Planners failed:    0
  Failures: none

Valid triplets:     11
Invalid triplets:   2
  Writer failures: HONEST-01/r1, NM-03/r3

── PER-ARM STATISTICS ──
  F (Full JSON): n=11 mean=1970 min=978 max=2825 total=21677
  C (Chapter Architect): n=11 mean=2061 min=1523 max=2432 total=22679
  N (Narrative Projection): n=11 mean=1762 min=1194 max=2711 total=19389
  N/C length ratio: 85%
  N/F length ratio: 89%

── PER-SCENE BREAKDOWN ──
  CO-04: F=1438 (n=3) | C=2056 (n=3) | N=1510 (n=3)
  CO-05: F=2127 (n=2) | C=2307 (n=2) | N=1821 (n=2)
  HONEST-01: F=2012 (n=1) | C=2330 (n=1) | N=1194 (n=1)
  MULTI-01: F=2811 (n=1) | C=2432 (n=1) | N=1842 (n=1)
  NM-03: F=2701 (n=2) | C=2037 (n=2) | N=2330 (n=2)
  ROMANCE-02: F=1441 (n=2) | C=1529 (n=2) | N=1759 (n=2)

── ALL VALID TRIPLETS ──
  CO-04 r1: F=1791 C=2204 N=1256 [F→C→N]
  CO-04 r2: F=978 C=2107 N=1586 [F→N→C]
  CO-04 r3: F=1546 C=1859 N=1690 [C→F→N]
  CO-05 r1: F=1919 C=2267 N=1789 [F→C→N]
  CO-05 r3: F=2336 C=2348 N=1853 [N→C→F]
  HONEST-01 r2: F=2012 C=2330 N=1194 [N→F→C]
  MULTI-01 r3: F=2811 C=2432 N=1842 [C→F→N]
  NM-03 r1: F=2577 C=2014 N=1950 [F→C→N]
  NM-03 r2: F=2825 C=2060 N=2711 [F→N→C]
  ROMANCE-02 r1: F=1770 C=1523 N=1615 [C→N→F]
  ROMANCE-02 r2: F=1112 C=1535 N=1903 [N→F→C]

── PREREGISTRATION CHECK ──
  ≥ 15 complete triplets: FAIL (11/15)
  ≥ 2 triplets per scene: FAIL
    CO-04: 3/2 ✓
    CO-05: 2/2 ✓
    HONEST-01: 1/2 ✗
    MULTI-01: 1/2 ✗
    NM-03: 2/2 ✓
    ROMANCE-02: 2/2 ✓
  No cross-arm contamination: PASS (verified by design — separate sessions)
  Blind pack no arm leak: PASS (randomized X/Y/Z labels)
  Deterministic compiler: PASS (30 unit tests, byte-identical re-runs)
  Old modes unchanged: PASS (591 test suite, 0 new failures)
  Overall engineering validity: INCONCLUSIVE

── PRELIMINARY OBSERVATIONS (not a substitute for blind review) ──
  1. N mean length (1693) is 14% below C (1988) and 17% below F (2041)
  2. N produces the shortest output in 6/10 triplets
  3. N also produces the longest output in 1/10 (NM-03 r2: 2711)
  4. C produces the longest output in 7/10 triplets
  5. F produces the longest output in 2/10 triplets
  6. All failures are A1 Planner (PLANNER_OUTPUT_CONTRACT_INVALID) or XML extraction
  7. No N-specific errors — N arm succeeds whenever F and C do
  8. HONEST-01 N=1194 is notably short — worth checking for premature stop

── BLIND EVALUATION ASSETS ──
  Blind pack: E:\3\novel-workbench\__evaluation\narrative_projection_compiler_v1_three_arm\blind\queue.json
  Private mapping: E:\3\novel-workbench\__evaluation\narrative_projection_compiler_v1_three_arm\blind\private_mapping.json
  Zhuque F: E:\3\novel-workbench\__evaluation\narrative_projection_compiler_v1_three_arm\zhuque\F.txt
  Zhuque C: E:\3\novel-workbench\__evaluation\narrative_projection_compiler_v1_three_arm\zhuque\C.txt
  Zhuque N: E:\3\novel-workbench\__evaluation\narrative_projection_compiler_v1_three_arm\zhuque\N.txt
  Zhuque all: E:\3\novel-workbench\__evaluation\narrative_projection_compiler_v1_three_arm\zhuque\all_randomized.txt