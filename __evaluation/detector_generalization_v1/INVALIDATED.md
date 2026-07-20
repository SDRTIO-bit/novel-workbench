# Invalidated run — do not analyse

This partial run used the Writer output cap (`1800`) for Planner calls.  Two
Planner candidates failed with `STRUCTURED_OUTPUT_TRUNCATED`, so it cannot
satisfy the required 12 shared Planner results.  The process was stopped after
26 Writer responses had been recorded.  The raw files remain for root-cause
audit only and must not be combined with the replacement batch.

Replacement evidence is written to `__evaluation/detector_generalization_v1_r1`
with Planner fixed at 4096 output tokens and Writer retained at 1800.
