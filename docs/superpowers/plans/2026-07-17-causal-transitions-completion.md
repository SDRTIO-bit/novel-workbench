# Causal Transitions Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete only the missing parts of the approved causal-transition design: detector-feedback UI and validation, targeted test coverage, evidence recording, and removal of development-only artifacts.

**Architecture:** Keep the existing five-stage generation workflow unchanged. Add a small detector-feedback client and a Judge-area panel that performs CRUD through the existing REST endpoints; validate feedback spans against the referenced candidate/version on the server. Preserve detector results as author-entered evidence only—never expose them to Writer, Critic, Reviser, or Judge prompts.

**Tech Stack:** React 18, TypeScript, TanStack Query, Vitest, FastAPI, Pydantic v2, SQLAlchemy async, SQLite/Alembic, pytest.

## Global Constraints

- Do not add a sixth Agent, detector-driven rewrite loop, long-term memory, or unrelated refactor.
- Do not change user-created prompt versions or existing chapter/candidate content.
- Keep `D data/chapters/.gitkeep` untouched; it predates this feature.
- Each behavioral change follows red → green TDD.
- Do not log API keys, provider credentials, or raw authorization headers.
- External detector results are manual evidence; a failed score must be retained and must not automatically alter text.

---

### Task 1: Harden detector-feedback validation and CRUD coverage

**Files:**
- Modify: `apps/api/app/schemas/detector_feedback.py`
- Modify: `apps/api/app/routers/detector_feedbacks.py`
- Modify: `apps/api/tests/test_runs_api.py`

**Interfaces:**
- `POST /api/detector-feedbacks` accepts ratios in `[0, 100]`, all-three total in `[99.5, 100.5]`, and spans with `start_paragraph <= end_paragraph`.
- A span must be within the paragraph count of the referenced candidate or chapter version.
- `PATCH /api/detector-feedbacks/{id}` revalidates the complete merged ratio set.

- [x] **Step 1: Write failing API tests**

```python
async def test_detector_feedback_rejects_out_of_range_span(api_client):
    response = await api_client.post('/api/detector-feedbacks', json={
        **valid_feedback,
        'spans': [{'start_paragraph': 99, 'end_paragraph': 100}],
    })
    assert response.status_code == 400

async def test_detector_feedback_patch_revalidates_merged_ratios(api_client):
    feedback = await create_feedback_with_ratios(api_client, 50, 25, 25)
    response = await api_client.patch(
        f"/api/detector-feedbacks/{feedback['id']}",
        json={'ai_ratio': 60},
    )
    assert response.status_code == 422
```

- [x] **Step 2: Run focused tests and verify they fail for missing validation**

Run: `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k detector_feedback -q`

Expected: failure because span bounds and merged PATCH ratios are not validated.

- [x] **Step 3: Implement minimal validation**

```python
class DetectorSpan(BaseModel):
    start_paragraph: int = Field(ge=1)
    end_paragraph: int = Field(ge=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.start_paragraph > self.end_paragraph:
            raise ValueError('起止段落顺序无效')
        return self
```

In the router, resolve the referenced candidate/version text, calculate numbered paragraphs, and reject a span whose `end_paragraph` exceeds that count. For PATCH, merge incoming ratios with the stored feedback ratios before applying the same total check.

- [x] **Step 4: Run focused tests and verify green**

Run: `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k detector_feedback -q`

Expected: all detector-feedback tests pass.

### Task 2: Add a bounded detector-feedback client and Judge-area panel

**Files:**
- Create: `apps/web/src/api/detectorFeedbacks.ts`
- Create: `apps/web/src/features/generation/DetectorFeedbackPanel.tsx`
- Create: `apps/web/src/features/generation/DetectorFeedbackPanel.test.tsx`
- Modify: `apps/web/src/types/generation.ts`
- Modify: `apps/web/src/features/generation/WorkflowPanel.tsx`

**Interfaces:**
- `listDetectorFeedbacks(projectId, chapterId?)`, `createDetectorFeedback(payload)`, `updateDetectorFeedback(id, payload)`, `deleteDetectorFeedback(id)`.
- `DetectorFeedbackPanel` receives `projectId`, `chapterId`, `run`, and renders only in the Judge/final area.
- The panel lets the author choose one selected Writer/Reviser/Judge candidate or an accepted chapter version, enter detector name and ratios, add/remove span rows, and edit/delete saved feedback.

- [x] **Step 1: Write failing frontend tests**

```tsx
it('creates feedback for the selected Judge candidate', async () => {
  render(<DetectorFeedbackPanel projectId="p" chapterId="c" run={run} />)
  fireEvent.change(screen.getByLabelText('检测器名称'), { target: { value: '特邀测试' } })
  fireEvent.change(screen.getByLabelText('AI 特征比例'), { target: { value: '100' } })
  fireEvent.click(screen.getByRole('button', { name: '保存检测反馈' }))
  await waitFor(() => expect(createDetectorFeedback).toHaveBeenCalledWith(expect.objectContaining({
    candidate_id: 'judge-candidate', ai_ratio: 100,
  })))
})

it('deletes a saved feedback record', async () => {
  render(<DetectorFeedbackPanel projectId="p" chapterId="c" run={run} />)
  fireEvent.click(screen.getByRole('button', { name: '删除检测反馈 feedback-1' }))
  await waitFor(() => expect(deleteDetectorFeedback).toHaveBeenCalledWith('feedback-1'))
})
```

- [x] **Step 2: Run the new test file and verify red**

Run: `cd apps/web; npx vitest run src/features/generation/DetectorFeedbackPanel.test.tsx`

Expected: fail because the client and component do not exist.

- [x] **Step 3: Implement the minimal client, types, and panel**

```ts
export interface DetectorFeedbackCreate {
  project_id: string
  chapter_id?: string
  run_id?: string
  candidate_id?: string
  chapter_version_id?: string
  detector_name: string
  human_ratio?: number
  suspected_ai_ratio?: number
  ai_ratio?: number
  spans: DetectorSpan[]
  notes?: string
}
```

Use TanStack Query keys `['detector-feedbacks', projectId, chapterId]`. Keep the panel collapsed by default. Candidate choices are selected Writer, Reviser, and Judge candidates only; accepted-version choice is offered only when `run.accepted_version_id` exists. No “improve score” action is added.

- [x] **Step 4: Run frontend tests and verify green**

Run: `cd apps/web; npx vitest run src/features/generation/DetectorFeedbackPanel.test.tsx src/features/generation/StagePanel.test.tsx`

Expected: all listed tests pass.

### Task 3: Complete causal-transition presentation tests and Judge warnings

**Files:**
- Modify: `apps/web/src/features/generation/StagePanel.tsx`
- Modify: `apps/web/src/features/generation/StagePanel.test.tsx`
- Modify: `apps/web/src/features/generation/WorkflowPanel.tsx`

**Interfaces:**
- Planner candidate displays 0–3 causal cards with trigger, next action, withheld inference, consequence, and next constraint.
- Critic displays causal audit status and protected paragraph ranges.
- Judge displays the four causal verdict flags and a warning when `necessary_information_lost` is true.

- [x] **Step 1: Write failing display tests**

```tsx
it('shows a planner causal transition without forcing one for an empty array', () => {
  renderPanel('planner', plannerCandidateWithOneTransition)
  expect(screen.getByText('证据 → 行动')).toBeInTheDocument()
  expect(screen.getByText('GR-0713')).toBeInTheDocument()
})

it('warns when Judge reports necessary information lost', () => {
  renderWorkflow(judgeCandidateWithInformationLost)
  expect(screen.getByText('修订稿丢失必要信息')).toBeInTheDocument()
})
```

- [x] **Step 2: Run tests and verify red**

Run: `cd apps/web; npx vitest run src/features/generation/StagePanel.test.tsx`

Expected: new assertions fail because structured views/warnings are absent.

- [x] **Step 3: Implement compact structured renderers**

Use parsed selected-candidate JSON only; preserve raw JSON in `CandidateView`. Add no new API call. Render only fields present in the contractual output, and keep empty arrays visually quiet.

- [x] **Step 4: Run focused tests and verify green**

Run: `cd apps/web; npx vitest run src/features/generation/StagePanel.test.tsx src/features/generation/DetectorFeedbackPanel.test.tsx`

Expected: all tests pass.

### Task 4: Record the observed external result and clean development-only artifacts

**Files:**
- Modify: `docs/validation/2026-07-17-causal-transitions-real-llm.md`
- Modify: `docs/validation/2026-07-17-causal-transitions-real-llm.json`
- Delete: `apps/api/check_validator.py`
- Delete: `apps/api/debug_test.py`
- Delete: `scripts/check_state.py`
- Delete: `scripts/debug_templates.py`
- Retain: `scripts/validation_run.py` only if it is documented as a reproducible validation helper; otherwise delete it.

**Interfaces:**
- The accepted Judge version has a detector-feedback record: human 0, suspected AI 0, AI 100, no invented human spans.
- The report states the causal-transition detector hypothesis failed for this sample and no automatic rewrite was performed.

- [x] **Step 1: Add backend evidence test**

```python
async def test_detector_feedback_can_record_full_ai_result_for_accepted_version(api_client):
    response = await api_client.post('/api/detector-feedbacks', json={
        **valid_version_feedback,
        'human_ratio': 0,
        'suspected_ai_ratio': 0,
        'ai_ratio': 100,
        'spans': [],
    })
    assert response.status_code == 201
```

- [x] **Step 2: Run focused test coverage and verify the accepted-version feedback path**

Run: `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k full_ai_result -q`

Expected: red before the completed reference validation is in place.

- [x] **Step 3: Implement only the required server behavior, run migration, then record the real result through the local API**

Use the accepted version ID `644e0bff-eebb-4de2-ac22-fa473f715735`, detector name `特邀测试`, ratios `0/0/100`, empty spans, and a note that the user manually reported a 100% AI result. Do not fabricate an artificial interval.

- [x] **Step 4: Delete the listed debug artifacts and retain only validation evidence**

Use `apply_patch` deletions. Do not touch `data/chapters/.gitkeep`.

- [x] **Step 5: Verify record and report**

Run: `cd apps/api; .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k detector_feedback -q`

Run a local API GET for `detector-feedbacks?project_id=f6d07df4-002d-44ed-82a6-19f3dc1d3c98&chapter_id=31031f88-3058-4d8c-984b-2d0d84e31d92` and confirm exactly one matching `0/0/100` record is present.

### Task 5: Final regression and truthful acceptance boundary

**Files:**
- Modify only if verification finds a failure.

- [x] **Step 1: Run full backend verification**

Run: `cd apps/api; .\venv\Scripts\python.exe -m pytest -q; .\venv\Scripts\alembic.exe upgrade head; .\venv\Scripts\alembic.exe current`

Expected: all tests pass and current revision equals head.

- [x] **Step 2: Run full frontend verification**

Run: `cd apps/web; npm run lint; npx vitest run; npx vite build`

Expected: all commands exit 0.

- [x] **Step 3: Inspect scope and secrets**

Run: `git diff --check; git status --short`.

Search changed documentation and scripts for API keys, Authorization headers, or provider secrets; report only the safe result.

- [x] **Step 4: Update the validation report’s final verdict**

State separately:

1. Engineering and UI/API behavior validated or not.
2. A real project-pipeline LLM run completed with mixed models, while all-Pro Reviser remained provider-blocked.
3. External detector hypothesis failed for the recorded sample (`0%` human / `100%` AI); no claim of detector improvement is permitted.
4. Full statistical 3×3 old/new external comparison remains a future manual evaluation, not an implementation blocker.
