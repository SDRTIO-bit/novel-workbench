# Current Phase

## Status

EVALUATION_BASELINE_V1_COMPLETED

## Evidence-based decision

Current evidence does not support the complete five-stage pipeline as the
default generation path.

Default path:

```text
Planner → Writer
```

Optional review path:

```text
Writer → Critic → author selects issues → Reviser
```

Judge provides comparison advice only. It does not create or select a final
draft automatically.

## Evaluation result

- Final anonymous blind preference: 3/4
- Fewer key Planner-contract errors than Writer: 1/4
- Important facts outside Planner added by Reviser: 0/4
- stop_state accurate: 3/4
- CASE-004 Reviser blind comparison regressed from Writer
- CASE-004 Judge output contract failed

## Current conclusion

The multi-stage pipeline has local diagnostic and fact-closure value, but has
not demonstrated that it is more reliable than a single Writer draft.

## Next phase

PIPELINE_VNEXT_WRITER_BRIEF

1. Repair Judge paragraph-label handling and retain failures as separate
   evidence.
2. Use a deterministic WriterBriefCompiler between Planner and Writer.
3. Do not send the complete Planner backend output to Writer.
4. Make Reviser patch-only; the server validates and applies patches.
5. Re-evaluate the same four cases, comparing baseline Writer with vNext
   Writer before treating Critic, Reviser, or Judge as primary win metrics.
