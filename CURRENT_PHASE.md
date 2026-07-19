# Current Phase

## Status

WRITER_BRIEF_AB_TEST_V1_PRECHECK_FAILED

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

## WRITER_BRIEF_AB_TEST_V1

All four reused cases stopped in the frozen preflight before any Writer call.
The deterministic compiler omits the full Planner JSON and places the brief at
the end of the Writer prompt, but it does not provide an explicit
`unknown_information`, `current_assumption`, or `assumption_basis` field and
has no declared active-project-facts cap.

Therefore no blind pair, contract comparison, token comparison, or pass-rate
claim exists for WriterBrief v1. This is an input-contract engineering failure,
not evidence that either baseline Writer or WriterBrief Writer writes better
prose.

## Next phase

WRITER_BRIEF_CONTRACT_DECISION_REQUIRED

The frozen A/B protocol cannot continue until the WriterBrief input contract is
explicitly decided. No Prompt, schema, stage, compiler, provider, or evaluation
standard was changed during this failed precheck.
