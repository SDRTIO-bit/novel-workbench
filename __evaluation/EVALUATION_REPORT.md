# GENERALIZATION_BATCH_V1 Evaluation Report

## Result

This batch does **not** establish that the multi-stage pipeline is more stable than a single Writer. It does establish a mixed result: the final composition wins anonymous comparison in three of four cases, but it reduces Planner-contract errors in only one of four and regresses in CASE-004.

| Case | Anonymous winner | Final source | Result |
| --- | --- | --- | --- |
| CASE-001 | B | Final composition | Final wins; exact stop fact repaired. |
| CASE-002 | A | Judge merged text | Final wins; prose becomes less explanatory. |
| CASE-003 | B | Judge merged text | Final wins; ending restraint improves. |
| CASE-004 | B | Reviser text | Final loses; Judge output contract failed. |

## Planner-contract audit

| Measure | Result | Threshold | Status |
| --- | ---: | ---: | --- |
| Final has fewer key contract errors than Writer | 1/4 | 3/4 | Fail |
| Final adds important facts outside Planner | 0/4 | 0/4 | Pass |
| Final stop state is present | 3/4 | 3/4 | Pass |
| Judge local choices avoid regression | 3/4 | 3/4 | Pass |

CASE-001 improves the required contact from an almost-contact to actual contact. CASE-002 removes direct narration of Lin Che's inner prohibitions. CASE-003 removes the direct speculation about Gu Yan's destination, but its core contract was already complete. CASE-004 loses to Writer in blind reading and has no valid Judge decision because the Judge output contained paragraph labels.

## Pipeline attribution

- Critic diagnoses were supported in all four cases.
- Reviser completely resolved selected issues only in CASE-002 and CASE-004; CASE-001 left the cost/commitment gap for manual source restoration, and CASE-003 retained one direct inner-monologue issue.
- Reviser introduced no material fact outside the Planner contract in any case.
- CASE-004 is the counterexample: the exported Reviser text is less natural than Writer, while Judge could not produce a valid decision.

## Cost and execution

| Case | Input tokens | Output tokens | Total latency (ms) | Pipeline status |
| --- | ---: | ---: | ---: | --- |
| CASE-001 | 95,982 | 55,108 | 857,703 | Existing benchmark export |
| CASE-002 | 17,072 | 4,773 | 53,421 | Completed |
| CASE-003 | 17,946 | 5,569 | 57,334 | Completed |
| CASE-004 | 19,500 | 6,609 | 65,589 | Judge contract failure |

No stage was retried and no frozen Prompt, schema, stage, candidate contract, or prior final composition was changed.

## What the evidence supports

The frozen pipeline can improve local prose restraint and exact stop-state delivery: it did so in CASE-001 to CASE-003. The current evidence does not support enabling it as a reliable default: it fails the Planner-contract-improvement threshold and CASE-004 shows a concrete final-text regression. This report records the failure without proposing a Prompt change from one case.

## CASE-004 Judge contract supplement

`CASE-004-JUDGE-CONTRACT-FIX` ran exactly one additional Judge call against the
original CASE-004 Planner, Writer, Critic, and Reviser candidates. The original
frozen evidence remains unchanged. The repaired service accepted the comparison,
removed legal paragraph labels from the suggested merged text, and recorded the
result separately under `supplemental/CASE-004-JUDGE-CONTRACT-FIX/`. It restores
Judge-as-advice availability; it does not change the baseline conclusion or make
Judge an automatic final-text selector.
