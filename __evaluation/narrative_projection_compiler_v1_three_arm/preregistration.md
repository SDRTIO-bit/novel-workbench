# Narrative Projection Compiler v1 — Three-Arm Experiment

## Preregistration

**Date:** 2026-07-21
**Experiment:** NARRATIVE_PROJECTION_COMPILER_V1_THREE_ARM
**Baseline HEAD:** a990542789583602bd0978329dd11a5f7c7a5926

---

## 1. Hypothesis

Reorganizing A1 Chapter Architect output into five narrative-access blocks
(NARRATION_ACCESS, FOREGROUND_KNOWLEDGE, BACKSTAGE_BEHAVIOR_ONLY,
PLANNED_STATE_DELTAS, STOP_STATE) — while removing chapter_position,
content_summary, plot_lines, reader_must_infer, reader_payoff,
hook_requirement, capacity_check, and related fields — should:

1. Reduce narrator overreach and explanatory narration by making POV
   boundaries explicit per character.
2. Maintain non-focus character behavioral continuity while withholding
   their internals.
3. Produce more interaction-driven information change (vs. passive
   realization).
4. Reduce verbatim translation of Planner state_change goals into prose.
5. Reduce micro-action slow-motion and post-stop_state tailing.

## 2. Arms

| Arm | Label | Writer Input |
|-----|-------|-------------|
| F   | Full JSON | Complete A1 parsed JSON (all fields) |
| C   | Chapter Architect Compiler | Existing `chapter_architect` mode
| N   | Narrative Projection Compiler | New `narrative_projection` mode |

All arms use:
- **Planner:** Chapter Architect v1 (A1)
- **Writer:** Sacrificial Preflight Fusion v9 (W9)
- **Frozen params:** temperature=0.7, top_p=1.0, max_output_tokens=6000

## 3. Scenes

### Stage 1 (smoke — 4 scenes × 1 replica)

| Case ID | Title | Focus Character |
|---------|-------|----------------|
| NM-03 | 洗衣房的滚筒 | 方笛 |
| ROMANCE-02 | 未读消息 | 夏知 |
| CO-04 | 操场上错拿的水壶 | 路远 |
| CO-05 | 快递架上的同名包裹 | 向暖 |

### Stage 2 (formal — 6 scenes × 3 replicas)

Same as Stage 1 plus 2 new scenes:

| Case ID | Title | Focus Character | Non-Focus Trait |
|---------|-------|----------------|-----------------|
| MULTI-01 | 排练室的迟到 | 苏瑾 | Multiple non-focus characters with varying degrees of hidden info |
| HONEST-01 | 共享文档的编辑冲突 | 林子 | Non-focus character has NO withheld info, NO lies, NO avoidance |

HONEST-01 is specifically designed to test whether the N Compiler fabricates
suspicion behaviors ("模糊回答", "眼神回避", etc.) for a character who
has nothing to hide.

## 4. Success Criteria (Engineering)

1. New Compiler is purely deterministic (no LLM, no DB access).
2. All new unit tests pass.
3. Old Compiler modes produce identical output.
4. Production defaults unchanged.
5. Stage 1: 4/4 planners succeed, 12/12 stories extracted.
6. Stage 2: ≥ 15 complete triplets, ≥ 2 per scene.
7. Same-group triplets have identical planner_output_sha256.
8. No cross-arm context contamination.
9. Blind pack does not leak arm mapping.

## 5. Success Criteria (Literary — Blind Assessment)

N is a positive signal only if ALL of:

1. N reduces non-focus-character direct mental access vs. F and C in most pairs.
2. Non-focus character behavioral continuity does not degrade noticeably.
3. Dialog/action more frequently produces information/choice/constraint changes.
4. N does NOT universally convert ordinary characters into "模糊回答/眼神回避" suspects.
5. N does NOT more frequently copy BACKSTAGE_TARGET_DELTA verbatim into prose.
6. Overall publishability preference not lower than F/C.
7. Mean story length decrease ≤ 15% (not a primary metric).

## 6. Judging Criteria (per triplet)

Each triplet receives 3 randomized labels (X, Y, Z) and is judged on:

1. Overall publishability ranking
2. Non-focus character behavioral continuity ranking
3. Narrator overreach level: low/medium/high
4. Whether dialog changes information or choices
5. Presence of explanatory restatement
6. Whether Delta is directly concluded in narration
7. Whether ordinary actions are slow-motioned
8. Whether ordinary characters appear suspicious/evasive
9. Whether stop_state is followed by tailing
10. Final preference and reason

## 7. Zhuque

Secondary engineering signal only. Submitted after manual blind review.

## 8. Deferred (NOT in scope)

- A2 Planner
- W9 Addendum
- ACTIVE_PROPS extraction
- Natural Scene Realization Addendum
- Modifying A1 Prompt, A1 Schema, W9 Prompt, W9 XML protocol
- Modifying Critic, Reviser, Judge, Ledger, Frontend
- Production default pipeline changes

## 9. N Compiler — Explicitly Removed Fields

The following A1 fields are preserved in audit assets but NOT passed to N-arm Writers:

- chapter_position, reader_payoff, hook_requirement
- content_summary, plot_lines, reader_must_infer
- hook_detail, hook_strength, capacity_check, capacity_reason
- forbidden_padding, architect_contract_version

## 10. Error Codes

- NARRATIVE_PROJECTION_PLAN_MISSING
- NARRATIVE_PROJECTION_CHARACTERS_MISSING
- NARRATIVE_PROJECTION_FOCUS_MISSING
- NARRATIVE_PROJECTION_FOCUS_NOT_FOUND
- NARRATIVE_PROJECTION_ACTIONS_MISSING
- NARRATIVE_PROJECTION_STOP_STATE_MISSING
