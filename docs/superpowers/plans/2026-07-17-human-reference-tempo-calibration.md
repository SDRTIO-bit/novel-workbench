# Human-reference tempo calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pipeline’s mandatory chapter-completion pattern with event-responsive tempo guardrails for original scenes.

**Architecture:** Planner emits optional `tempo_guardrails`; ContextService makes them available to every later stage; Writer uses scene-response rules instead of fixed hook/payoff/hook beats. Critic, Reviser, and Judge gain bounded diagnostics and selected-issue validation.

**Tech Stack:** Python, FastAPI, Pydantic v2, SQLAlchemy, pytest, React, TypeScript, Vitest, existing DeepSeek OpenAI-compatible provider.

## Global Constraints

- Never insert, retain, paraphrase, or reproduce the reference novel’s text, plot, characters, sentence order, or distinctive wording.
- Do not use paragraph length, dialogue ratio, or an external detector as a generation target.
- Historical planner outputs without tempo data stay valid.
- Keep causal cards only for local action logic; do not add agents, vector search, or automatic rewrite loops.
- The acceptance test must use the project HTTP pipeline and real `deepseek-chat`.

## File map

- `apps/api/app/llm/output_contracts.py`: contracts and enum values.
- `apps/api/app/schemas/context.py`, `apps/api/app/schemas/generation.py`: stage override/context fields and allowlist.
- `apps/api/app/services/context_service.py`, `apps/api/app/services/generation_service.py`: propagation and Judge truthfulness check.
- `apps/api/app/prompts/defaults.py`, `apps/api/app/llm/mock.py`: prompt behavior and valid Mock outputs.
- `apps/api/tests/test_output_contracts.py`, `test_context_service.py`, `test_prompts.py`, `test_runs_api.py`: regression coverage.
- `apps/web/src/types/generation.ts`, `apps/web/src/features/generation/StagePanel.tsx`, `StagePanel.test.tsx`: optional UI cards.
- `docs/validation/2026-07-17-human-reference-tempo-real-llm.json`: sanitized real-run evidence.

## Interfaces

```python
class TempoGuardrails(BaseModel):
    entry_pressure: str = Field(min_length=1)
    dominant_disruption: str = Field(min_length=1)
    allowed_viewpoint_misread: str = ""
    disclosure_cap: int = Field(default=1, ge=0, le=1)
    must_remain_unclassified: list[str] = Field(default_factory=list)
    stop_after: str = Field(min_length=1)

class TempoProfileCheck(BaseModel):
    starts_in_motion: bool = True
    disruption_interrupts_action: bool = True
    viewpoint_misread_is_actionable: bool = True
    disclosure_cap_respected: bool = True
    unclassified_facts_preserved: bool = True
    ending_stops_without_summary: bool = True
    formulaic_completion_risk: Literal["low", "medium", "high"] = "low"
```

The two new valid revision operations are exactly `de_label` and `de_chain`.

---

### Task 1: Contracts and context propagation

**Files:** Modify `output_contracts.py`, `schemas/context.py`, `schemas/generation.py`, `context_service.py`, `generation_service.py`. Test `test_output_contracts.py`, `test_context_service.py`.

- [ ] **Step 1: Write failing contract tests**

Add a valid planner fixture with `tempo_guardrails` containing entry pressure, disruption, a limited misread, cap `1`, one unclassified fact, and stop condition. Assert `validate_planner_output` returns the cap. Parametrize invalid cap `2`, missing `stop_after`, and a non-string unclassified entry; each must raise `PLANNER_OUTPUT_CONTRACT_INVALID`. Add a Critic fixture with a low-risk `tempo_profile_check` and assert it validates.

- [ ] **Step 2: Verify failure**

Run `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_output_contracts.py -q`.

Expected: the new fields are absent or invalid.

- [ ] **Step 3: Implement fields and propagation**

Import `Literal`; implement the two models above in `output_contracts.py`; add `tempo_guardrails: TempoGuardrails | None = None` to `PlannerOutput` and `tempo_profile_check: TempoProfileCheck | None = None` to `CriticOutput`. Validate that every unclassified item is a non-empty string.

Add `tempo_guardrails: dict | None = None` to `ContextPreviewRequest` and `StageOverrideRequest`; append `de_label`, `de_chain` to backend `REVISION_OPERATIONS`. In `ContextService.assemble`, set `variables["tempo_guardrails"]` to `json.dumps(..., ensure_ascii=False, indent=2)` or `""`, and add it to `untouchable`. In `_build_context_request`, propagate the override and replace it with selected Planner JSON only when `scene_plan["tempo_guardrails"]` is a dictionary.

- [ ] **Step 4: Add context test and verify pass**

Assemble a context with guardrails; assert rendered system prompt contains `dominant_disruption` and sources include `tempo_guardrails`. Run `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_output_contracts.py tests/test_context_service.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit**

Run `git add apps/api/app/llm/output_contracts.py apps/api/app/schemas/context.py apps/api/app/schemas/generation.py apps/api/app/services/context_service.py apps/api/app/services/generation_service.py apps/api/tests/test_output_contracts.py apps/api/tests/test_context_service.py; git commit -m "feat: add tempo guardrail contracts"`.

### Task 2: Prompt behavior and Mock contracts

**Files:** Modify `prompts/defaults.py`, `llm/mock.py`. Test `test_prompts.py`, `test_runs_api.py`.

- [ ] **Step 1: Write failing regression tests**

Assert the built-in Writer system prompt contains `场景响应规则` and `{{tempo_guardrails}}`, but contains none of `开场钩子：`, `爽点释放：`, `结尾钩子：制造新的`. Extend the Mock E2E flow to assert Planner output contains `tempo_guardrails.disclosure_cap == 1` and Critic output contains a valid risk value.

- [ ] **Step 2: Verify failure**

Run `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_prompts.py tests/test_runs_api.py -q`.

Expected: prompt/Mock assertions fail.

- [ ] **Step 3: Replace only the Writer’s four-beat block**

Delete `章节结构要求：` and its fixed opening/development/payoff/ending-hook requirements. Insert this exact behavior:

```text
场景响应规则：
1. 从 tempo_guardrails.entry_pressure 对应的具体行动或回避开始；不要先罗列天气、地点、外貌和背景。
2. dominant_disruption 出现时必须打断正在进行的事情；先写人物反应和实际处理。
3. 允许当前视角作出不完整或错误判断；该判断必须改变下一步，旁白不得立刻纠正为正确答案。
4. 不得仅为快捷塑造人物而给职业、阶层、性格或关系贴标签。
5. 遵守 disclosure_cap 与 must_remain_unclassified；对象可被看见，其含义不必命名、解释或接成第二条线索。
6. 到 stop_after 的新实际问题成立时停止；不得追加主题总结、悬念比喻或第二次即时破译。
```

Add `## 节奏护栏` plus `{{tempo_guardrails}}` to every stage template that uses the selected plan. Planner asks for optional guardrails. Critic adds five types: `narrator_character_label`, `clue_conveyor_belt`, `formulaic_escalation`, `premature_classification`, `closing_summary_hook`; direct thought is allowed when it is a limited actionable judgment. Reviser adds bounded `de_label` and `de_chain`. Judge states that unselected issues cannot be resolved.

Update Mock: Planner emits valid guardrails; Critic emits a valid tempo check plus new issue types; Reviser patches only selected IDs; Judge resolves only selected IDs.

- [ ] **Step 4: Verify pass and commit**

Run `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_prompts.py tests/test_runs_api.py -q; git add apps/api/app/prompts/defaults.py apps/api/app/llm/mock.py apps/api/tests/test_prompts.py apps/api/tests/test_runs_api.py; git commit -m "feat: calibrate prompts for responsive scene tempo"`.

Expected: PASS with no Mock structured-output failures.

### Task 3: Enforce truthful Judge outcomes

**Files:** Modify `output_contracts.py`, `generation_service.py`. Test `test_output_contracts.py`, `test_runs_api.py`.

- [ ] **Step 1: Write failing tests**

Parametrize Critic validation over all five new issue types and appropriate operations. In HTTP E2E, select only `I01`, monkeypatch the provider so Judge reports `I02` as `resolved`, and assert the candidate `error_code` equals `JUDGE_UNSELECTED_ISSUE_RESOLVED`.

- [ ] **Step 2: Verify failure**

Run `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_output_contracts.py tests/test_runs_api.py -q`.

Expected: the old service accepts the false resolution.

- [ ] **Step 3: Implement exact check**

Add the five enum values to `CriticIssueType`, and `de_label`, `de_chain` to `RevisionOperation`. After Judge `validate_stage_output`, call:

```python
async def _validate_judge_issue_results(self, run_id: str, judge_output: dict) -> None:
    critic_step = await self.repo.get_step(run_id, "critic")
    selected_ids = set(json.loads(critic_step.selected_issue_ids_json or "[]")) if critic_step else set()
    for result in judge_output.get("issue_results", []):
        if result.get("status") == "resolved" and str(result.get("issue_id", "")) not in selected_ids:
            raise ValueError("JUDGE_UNSELECTED_ISSUE_RESOLVED: Judge marked an unselected issue resolved")
```

Preserve that error prefix in the existing exception handler; other validation errors retain `{STAGE}_OUTPUT_CONTRACT_INVALID`.

- [ ] **Step 4: Verify pass and commit**

Run `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_output_contracts.py tests/test_runs_api.py -q; git add apps/api/app/llm/output_contracts.py apps/api/app/services/generation_service.py apps/api/tests/test_output_contracts.py apps/api/tests/test_runs_api.py; git commit -m "fix: reject unselected judge issue resolutions"`.

Expected: invalid Judge output is persisted as failed and cannot be selected.

### Task 4: Render tempo results in the UI

**Files:** Modify `apps/web/src/types/generation.ts`, `apps/web/src/features/generation/StagePanel.tsx`. Test `StagePanel.test.tsx`.

- [ ] **Step 1: Write failing UI tests**

Render Planner output with guardrails and assert `节奏护栏`, `主异常`, and `单次披露上限：1`. Render Critic output with high risk and assert `公式化完成风险：高`. Render a historical candidate with no tempo values and assert the cards are absent.

- [ ] **Step 2: Implement compact optional cards**

Append `de_label` and `de_chain` to TypeScript `REVISION_OPERATIONS`. Add `asRecord` and `asStrings` helpers. Compose—not replace—the existing causal cards with a Planner card showing the six guardrail fields and a Critic card showing six booleans plus mapped low/medium/high risk. Both must return `null` when fields are absent.

- [ ] **Step 3: Verify pass and commit**

Run `cd apps/web; npm test -- --run src/features/generation/StagePanel.test.tsx; npm run lint; npm run build; git add apps/web/src/types/generation.ts apps/web/src/features/generation/StagePanel.tsx apps/web/src/features/generation/StagePanel.test.tsx; git commit -m "feat: show tempo guardrails in workflow"`.

Expected: all commands exit 0.

### Task 5: Regression and real DeepSeek acceptance

**Files:** Create `docs/validation/2026-07-17-human-reference-tempo-real-llm.json`.

- [ ] **Step 1: Run all checks**

Run `cd apps/api; .\venv\Scripts\python.exe -m pytest -q; cd ..\web; npm test; npm run lint; npm run build`.

Expected: all commands exit 0.

- [ ] **Step 2: Create a validation workflow without overwriting custom prompts**

Restore current built-in defaults through the existing prompt endpoint, duplicate the selected workflow as `人工节奏校准`, update its five step prompt-version IDs to the restored versions, and use that profile for validation. Record only IDs, never keys.

- [ ] **Step 3: Run a fully original HTTP pipeline**

Generate a science-fiction chapter: mechanic Lin Yu returns a failed survey rover before shift handover; tapping starts in its sealed coolant pipe; Lin Yu mistakenly assumes a loose valve and cuts hangar-door power; the chapter stops when the door panel treats the rover serial number as crew authorization. Do not use any reference-book event.

Select only local Critic issues. If Critic reports high `formulaic_escalation`, record `scene_rewrite` rather than pretending local revision repaired it.

- [ ] **Step 4: Record evidence and commit**

The evidence JSON contains policy, project/chapter/run/workflow/candidate/prompt-version IDs, model, retry count, guardrail presence, selected operations, final decision, and `has_internal_paragraph_labels: false`. It sets `external_detector.executed: false` unless the user manually tests. Run `git add docs/validation/2026-07-17-human-reference-tempo-real-llm.json; git commit -m "test: record tempo calibration real llm run"; git status --short`.

## Self-review

- Covers reference isolation, five stages, Mock, UI, local tests, and real HTTP DeepSeek validation.
- Uses identical names for `tempo_guardrails`, `tempo_profile_check`, `de_label`, and `de_chain` across tasks.
- Contains no TODO/TBD placeholders; runtime IDs are intentionally captured from the local API.
