# Human-reference tempo calibration design

**Date:** 2026-07-17  
**Status:** Proposed — implementation must not begin until this document is reviewed and approved.

## 1. Problem and evidence

The causal-transition release made the pipeline more logically explicit, but did not improve the external detector result. A real DeepSeek pipeline run for `雨夜当铺 / 第一章 雨夜赎镯` returned 25.38% explicit AI traits and 74.62% suspected AI traits in the external detector.

The chapter was not rejected because it lacked plot or prose. It exhibited a more fundamental pattern: it read like a complete, orderly answer to a chapter-writing assignment.

Observed pipeline pressures:

- Writer requires a fixed `opening hook -> development -> payoff -> ending hook` structure.
- Planner pre-specifies evidence, action, consequence, and next constraint.
- Critic and Judge prioritize contract completion, so a chapter can be highly compliant while mechanically tidy.
- Reviser can only perform local corrections and cannot change an over-designed draft skeleton.

An author-supplied, human-written local reference (`末日降临？我先降临！.txt`) is used only as an analysis corpus. It will never be inserted into prompts, stored as a project asset, copied, paraphrased scene-by-scene, or used to reproduce its characters, plot, sentence order, or recognizable expression.

The first chapter’s measurable surface profile is useful as a non-proprietary reference:

- 43 of its first 90 non-empty paragraphs are 20 characters or fewer;
- 22 of those paragraphs contain dialogue;
- the average paragraph length is about 24.4 characters;
- it allows direct, partial, and sometimes mistaken viewpoint judgments instead of converting every inference into an authorial conclusion;
- interruptions and reactions create the next event before the previous event is fully interpreted.

These figures are not quality targets and must not become hard generation quotas. They identify a direction to test: less chapter-complete, more event-responsive prose.

## 2. Goal and non-goals

### Goal

Make the pipeline capable of generating an **original** first chapter whose event sequence is less formulaic: one immediate pressure, one dominant abnormal event, character-specific imperfect reactions, and fewer narrator-managed explanations. The change must preserve story clarity and existing information-boundary controls.

### Non-goals

- Do not copy, retell, rewrite, or imitate the reference novel’s plot, characters, scene sequence, dialogue, or wording.
- Do not optimize directly against an external detector or make a detector score an automatic rewrite target.
- Do not require a particular paragraph count, dialogue ratio, error rate, or short-sentence ratio.
- Do not add a new agent, vector store, long-term memory system, or visual workflow editor.
- Do not remove the existing causal-transition feature; narrow its role to local action logic.

## 3. Chosen approach: tempo profile, not source imitation

Three approaches were considered:

1. **Put the human novel into Writer context.** This would be likely to cause copyright-adjacent imitation and would not demonstrate whether the pipeline can generate an independent story. Rejected.
2. **Tune a large banned-phrase list to the detector.** This creates fragile avoidance language and teaches the model to route around surface patterns. Rejected.
3. **Change pipeline incentives using an abstract tempo profile.** The profile controls only event handling and editorial diagnosis, while all story facts remain original. Chosen.

The profile is a stable set of behavioral constraints, not a voice imitation:

```text
Start with a person already doing or avoiding a concrete thing.
Let an interruption or object change the immediate situation before background is completed.
Permit a viewpoint character to make an incomplete or wrong immediate guess.
Keep one abnormal event dominant; do not queue multiple clues for immediate explanation.
Let dialogue, interruption, and practical action carry the scene forward.
Stop after the new problem becomes actionable; do not attach a thematic suspense summary.
```

## 4. Pipeline changes

### 4.1 Planner: reduce chapter-programming

Keep character goals, knowledge boundaries, and causal transitions. Remove any requirement that every plan prepares a payoff and a fresh ending hook.

Add a structured `tempo_guardrails` object to the planner contract:

```json
{
  "entry_pressure": "A concrete action already in progress at the first paragraph.",
  "dominant_disruption": "The one event that makes the scene stop being ordinary.",
  "allowed_viewpoint_misread": "A plausible but unverified immediate interpretation.",
  "disclosure_cap": 1,
  "must_remain_unclassified": ["Facts the narrator must not classify or explain this chapter."],
  "stop_after": "The next practical problem becomes actionable."
}
```

Rules:

- `disclosure_cap` is normally `0` or `1`; it is a plan cap, not a prose count.
- Each causal transition must be optional. Use it only where a visible fact must change an action.
- Do not create causal cards for ordinary atmosphere, genre labels, or a clue whose meaning is immediately supplied.
- For a first chapter, planner may leave `ending_hook` empty when the disruption itself is sufficient.

### 4.2 Writer: replace fixed four-beat compliance

Remove the current mandatory `opening hook / development / payoff / ending hook` block.

Replace it with a small “scene responsiveness” block:

1. Begin with `entry_pressure`; do not spend an opening paragraph cataloguing place, weather, appearance, and backstory.
2. When `dominant_disruption` appears, let it interrupt the current action.
3. The viewpoint character may form an incomplete or wrong judgment, but it must lead to a practical response.
4. Do not label a character’s occupation, class, personality, or relationship unless a current action proves relevant to it.
5. Respect `disclosure_cap` and `must_remain_unclassified`; an object may be seen without its significance being named.
6. End at `stop_after`; do not append a reflective metaphor, theme statement, or a second newly decoded clue.

The writer still follows project facts, POV, must-not-deliver, and information boundaries. It receives only the abstract `tempo_guardrails`, never reference text or reference metadata.

### 4.3 Critic: diagnose formulaic completion, not directness alone

Add issue types:

- `narrator_character_label`: the narrator assigns a role/personality/class label where the current event does not require it.
- `clue_conveyor_belt`: more than the plan’s allowed number of clues are discovered, interpreted, and converted into new leads in one unbroken chain.
- `formulaic_escalation`: the scene advances through predictable “setup -> explanation -> reveal -> hook” beats rather than interruption and response.
- `premature_classification`: an abnormal object/event is identified or named before the viewpoint has enough usable evidence.
- `closing_summary_hook`: the ending interprets its own suspense instead of stopping on an actionable fact, choice, or interruption.

Direct internal thought is not automatically `show_vs_tell`. Critic must only flag it when it repeats evidence already sufficient for the reader or provides the author’s correct answer rather than an actionable, limited viewpoint judgment.

Add `tempo_profile_check` to Critic output:

```json
{
  "starts_in_motion": true,
  "disruption_interrupts_action": true,
  "viewpoint_misread_is_actionable": true,
  "disclosure_cap_respected": true,
  "unclassified_facts_preserved": true,
  "ending_stops_without_summary": true,
  "formulaic_completion_risk": "low | medium | high"
}
```

### 4.4 Reviser: add only two bounded operations

Add these operations to the existing allowed operation set:

- `de_label`: remove or turn an unsupported narrator label into a present-tense observation, action, or limited viewpoint judgment. It must not add decorative detail.
- `de_chain`: break one over-complete clue chain by restoring an unresolved object/fact or deleting a premature interpretation. It cannot change plot facts, invent a different mystery, or remove information needed to understand the action.

Both remain local-only operations. A chapter with high `formulaic_escalation` is a `scene_rewrite` case; Reviser must not pretend that 80%-preserving edits can repair its macrostructure.

### 4.5 Judge: reject a clean but pre-programmed result

Judge receives `tempo_guardrails` and Critic’s `tempo_profile_check`.

Add fields:

```json
{
  "formulaic_completion_reduced": true,
  "unclassified_fact_preserved": true,
  "ending_overexplains_itself": false,
  "revision_must_be_replanned": false
}
```

Judge must not mark an issue “resolved” if it was not selected for revision and the relevant paragraphs were not changed. This fixes the false resolution observed in run `10be0f6c-023d-412a-8337-2ea0c8bda59b`.

## 5. Data flow and compatibility

```text
Chapter contract
  -> Planner: ScenePlan + tempo_guardrails
  -> Writer: original project facts + ScenePlan + tempo_guardrails
  -> Critic: draft + tempo_profile_check + issues
  -> user selects only local issues
  -> Reviser: selected local operations
  -> Judge: verifies actual selected patches and tempo outcome
```

Existing saved scene plans remain compatible: missing `tempo_guardrails` are treated as `null`, and old plans keep their existing behavior. New default prompt versions use the new object. The UI displays the guardrails in the existing Planner structured-result panel; no new project-level reference-text upload feature is introduced.

## 6. Validation

### Automated tests

- planner schema accepts valid guardrails and rejects invalid `disclosure_cap`, missing `stop_after`, or non-string `must_remain_unclassified` entries;
- prompt rendering tests assert the Writer no longer contains the mandatory four-beat chapter structure;
- Mock Provider produces valid guardrails and the new Critic/Judge fields;
- Critic contract tests accept every new issue type and reject an unsupported one;
- Reviser contract tests accept only `de_label` and `de_chain` as new operations;
- Judge service test proves unselected, unchanged issues cannot be reported as resolved;
- frontend test renders `tempo_guardrails` and `tempo_profile_check` safely when absent or present.

### Real LLM acceptance run

Use the configured real `deepseek-chat` provider, through the HTTP pipeline—not a direct ad-hoc call—to generate one original science-fiction first chapter. It must use a new premise unrelated to both the reference novel and `雨夜当铺`.

Acceptance evidence records:

- stage prompt versions, model, candidate IDs, retries, and timestamps;
- whether Planner chose no more than one dominant disruption and one disclosure;
- whether Writer output contains no internal paragraph labels;
- Critic/Judge handling of selected versus unselected issues;
- a manual external-detector result recorded as feedback, if the user chooses to test it.

An external detector percentage is observational evidence only. Success is not declared solely because a detector becomes green; failure is not hidden if it remains high.

## 7. Failure handling

- If Planner cannot satisfy guardrails and the chapter contract together, it returns a contract error rather than inventing extra revelations.
- If Critic finds high `formulaic_escalation`, it returns `scene_rewrite`; the UI must not offer `de_chain` as a fake local fix.
- If Judge receives an issue not in the selected revision set, it can only label it `unresolved` or `manual_review`, never `resolved`.
- If real LLM output violates structured contracts, preserve the failed candidate and retry only after a visible, targeted schema correction.

## 8. Scope of the implementation

In scope: default prompt versions, Planner/Critic/Judge contracts, Reviser operations, Mock Provider, rendering of the two new structured objects, unit tests, and one real LLM acceptance run.

Out of scope: importing the reference novel into the application, copyright-sensitive style imitation, detector automation, unrelated schema redesign, and automatic rewrite loops.
