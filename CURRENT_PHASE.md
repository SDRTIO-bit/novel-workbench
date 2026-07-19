# Current Phase

## Status

WRITER_BRIEF_AB_TEST_V1_COMPLETED

## Evidence-based decision

Current evidence does not support the complete five-stage pipeline as the
default generation path.

Default product path:

```text
Planner → WriterBriefCompiler → Writer
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

The prior precheck finding was corrected as an input-contract alignment issue:
the canonical field is `unknown_facts`, and `current_assumption` plus
`assumption_basis` are conditionally empty. The compiler now uses one
canonical validation path, retains no full Planner JSON, and caps deterministic
active project facts at five.

The four saved Planner candidates passed preflight and each received exactly
one WriterBrief Writer call. No Planner, Critic, Reviser, Judge, TGbreak,
retry, or candidate selection occurred.

- vNext blind wins: 3/4; losses: 1/4
- vNext has fewer key Planner-contract errors: 3/4
- Important Planner-external facts in vNext: 0/4
- vNext stop facts accurate: 4/4
- vNext input tokens: 5,101 versus baseline 10,262
- vNext latency: 50,824 ms versus baseline 41,908 ms

The frozen primary, blind, and safety gates pass. This supports retaining the
deterministic WriterBrief path for these evaluated cases; it does not support a
claim about broader scene distributions or downstream review stages.

## Next phase

WRITER_BRIEF_AB_TEST_V1_RECORDED

The next decision should use additional held-out cases if broader reliability
or latency claims are required. This report does not change Prompt, provider,
or downstream-stage evaluation standards.
