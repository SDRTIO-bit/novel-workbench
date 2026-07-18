# TGbreak Writer Adapter Implementation Plan

**Goal:** Install the imported TGbreak Core prompt pack as an optional prompt mode inside the existing Writer stage without adding a workflow, stage, or provider call.

**Baseline:** `main@97306b70dd2468ca60b2d321543e35ef1df63a71`, with TGbreak Core cherry-picked from `ed374bc67c92b4eb78ce493888812e9eb6203110`.

## Constraints

- Keep the stage graph exactly `planner`, `writer`, `critic`, `reviser`, `judge`.
- Default and missing `writer_prompt_mode` to `builtin`.
- Reuse the variables already assembled by `ContextService`; do not create a second planning or context data source.
- Resolve imported preset/profile rows from the database and never modify the source preset.
- Run TGbreak through the existing `GenerationService` provider boundary and persist a normal Writer candidate.
- Store TGbreak notes and provenance in `tgbreak_output_records`; downstream stages consume only `GenerationCandidate.text_output`.
- Send `reasoning_mode=disabled` only for TGbreak Writer requests and never retry a format failure.

## Test-first tasks

1. Add integration tests for missing/default builtin mode, builtin transport isolation, workflow duplication, and non-Writer validation.
2. Add adapter tests proving the existing project documents, history, chapter tail, selected Planner output/candidate ID, and user instruction map deterministically to `Story setting`, `interaction_record`, `ai_last_output`, and `peip`.
3. Add a simulated TGbreak Writer execution test covering ordered messages, real source SHA, standard candidate fields, output-record provenance, candidate selection, and Critic input isolation.
4. Add format-failure coverage proving one call, failed Writer candidate, raw response retention, and no downstream-selectable output.
5. Implement the minimal schema, migration, database reconstruction, request transport, adapter, and `GenerationService` branch needed to pass those tests.
6. Run focused tests, full `python -m pytest -q`, and the real preset dry-run without any model invocation.
