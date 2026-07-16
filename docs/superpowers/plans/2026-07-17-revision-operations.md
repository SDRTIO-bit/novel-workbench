# 局部修订操作 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在五步小说工作流中，让 Critic 为每个问题推荐局部修订操作，作者可改选，Reviser 按最终操作定点修订。

**Architecture:** 保持五阶段与既有提示词版本体系不变。Critic 问题新增 `recommended_operation`；`GenerationStep` 另存作者最终选择的映射；上下文装配器把完整问题和 `selected_operation` 传入 Reviser。React 在 Critic 问题卡中提供操作选择器，并继续通过既有“确认问题”接口提交选择。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy 2、Alembic、SQLite、React 19、TypeScript、TanStack Query、Vitest、pytest、Playwright。

## Global Constraints

- 仅支持 `naturalize`、`tighten`、`clarify`、`voice_align`、`ground_detail`、`rhythm_adjust`、`diction_refine`、`project_style_align` 八种操作。
- 不新增 Agent、操作管理页、自动多轮修订或全文润色。
- 既有仅含 `issue_ids` 的 API/MCP 调用必须仍可用，缺省时采用 Critic 推荐操作。
- Reviser 不得改变剧情事实、信息边界、关系阶段、叙事视角、场景结果或受保护段落。
- 所有行为变更必须先有失败测试；每项任务完成后运行其测试并提交。
- 完成时必须运行本地完整验收，并以已配置的非 Mock LLM 跑真实五阶段链路；不得记录或输出任何 API Key。

---

## 文件地图

| 文件 | 责任 |
| --- | --- |
| `apps/api/app/schemas/generation.py` | 定义操作常量、问题选择请求与 API 输出字段。 |
| `apps/api/app/models/generation.py` | 持久化每个 Critic step 的作者操作映射。 |
| `apps/api/alembic/versions/b9c5d75f8a31_add_selected_issue_operations.py` | 为现有数据库添加可空 JSON 文本列。 |
| `apps/api/app/services/generation_service.py` | 验证选择、持久化映射，并在 Reviser 上下文中组合完整选题。 |
| `apps/api/app/routers/runs.py` | 将 `operation_by_issue` 交给服务层。 |
| `apps/api/app/prompts/defaults.py` | 强制 Critic 输出推荐操作，并为 Reviser 写入八种受控操作说明。 |
| `apps/api/app/llm/mock.py` | 让模拟 Critic 输出合法操作，保证端到端流程可测。 |
| `apps/api/tests/test_runs_api.py` | 覆盖 API 选择、回退、验证、上下文和 Mock 五阶段流程。 |
| `apps/web/src/types/generation.ts` | 暴露操作联合类型、Critic 问题与选择请求类型。 |
| `apps/web/src/api/runs.ts` | 向确认问题 API 发送操作映射。 |
| `apps/web/src/features/generation/StagePanel.tsx` | 显示推荐操作，允许作者逐项改选并提交。 |
| `apps/web/src/features/generation/StagePanel.test.tsx` | 验证默认推荐、改选和请求载荷。 |

### Task 1: 持久化并验证作者的操作选择

**Files:**
- Modify: `apps/api/app/schemas/generation.py`
- Modify: `apps/api/app/models/generation.py`
- Create: `apps/api/alembic/versions/b9c5d75f8a31_add_selected_issue_operations.py`
- Modify: `apps/api/app/services/generation_service.py`
- Modify: `apps/api/app/routers/runs.py`
- Modify: `apps/api/app/llm/mock.py`
- Test: `apps/api/tests/test_runs_api.py`

**Interfaces:**
- Produces: `REVISION_OPERATIONS: tuple[str, ...]` and `SelectIssuesRequest.operation_by_issue: dict[str, str]`.
- Produces: `GenerationStep.selected_issue_operations_json: str | None`.
- Produces: `GenerationService.select_critic_issues(run_id, issue_ids, operation_by_issue)`.
- Consumed by Task 2 when assembling Reviser context and Task 3 when serialising UI requests.

- [ ] **Step 1: Write the failing API tests**

Add a helper that executes and selects the three upstream Mock stages, then assert the selected Critic step exposes both persisted JSON fields.

```python
async def _run_to_selected_critic(client):
    project_id = await _create_project(client)
    chapter_id = await _create_chapter(client, project_id)
    run = await client.post("/api/runs", json={"project_id": project_id, "chapter_id": chapter_id})
    run_id = run.json()["id"]
    for stage in ("planner", "writer", "critic"):
        candidate = await client.post(f"/api/runs/{run_id}/steps/{stage}/execute", json={})
        assert candidate.status_code == 200
        selection = await client.post(f"/api/runs/{run_id}/steps/{stage}/select/{candidate.json()['id']}")
        assert selection.status_code == 200
    return run_id


@pytest.mark.asyncio
async def test_select_issues_uses_critic_recommendation_by_default(api_client):
    run_id = await _run_to_selected_critic(api_client)

    response = await api_client.post(
        f"/api/runs/{run_id}/critic/select-issues",
        json={"issue_ids": ["I01"]},
    )

    assert response.status_code == 200
    run = (await api_client.get(f"/api/runs/{run_id}")).json()
    critic = next(step for step in run["steps"] if step["stage"] == "critic")
    assert json.loads(critic["selected_issue_ids_json"]) == ["I01"]
    assert json.loads(critic["selected_issue_operations_json"]) == {"I01": "tighten"}


@pytest.mark.asyncio
async def test_select_issues_persists_author_operation_override(api_client):
    run_id = await _run_to_selected_critic(api_client)

    response = await api_client.post(
        f"/api/runs/{run_id}/critic/select-issues",
        json={
            "issue_ids": ["I01"],
            "operation_by_issue": {"I01": "voice_align"},
        },
    )

    assert response.status_code == 200
    run = (await api_client.get(f"/api/runs/{run_id}")).json()
    critic = next(step for step in run["steps"] if step["stage"] == "critic")
    assert json.loads(critic["selected_issue_operations_json"]) == {"I01": "voice_align"}


@pytest.mark.asyncio
async def test_select_issues_rejects_invalid_or_unselected_operation_mapping(api_client):
    run_id = await _run_to_selected_critic(api_client)

    invalid = await api_client.post(
        f"/api/runs/{run_id}/critic/select-issues",
        json={"issue_ids": ["I01"], "operation_by_issue": {"I01": "rewrite_everything"}},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_REVISION_OPERATION"

    unselected = await api_client.post(
        f"/api/runs/{run_id}/critic/select-issues",
        json={"issue_ids": ["I01"], "operation_by_issue": {"I02": "tighten"}},
    )
    assert unselected.status_code == 400
    assert unselected.json()["error"]["code"] == "ISSUE_OPERATION_NOT_SELECTED"
```

- [ ] **Step 2: Run the new API tests and verify RED**

Run: `cd apps/api && .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k "select_issues_uses_critic_recommendation or select_issues_persists_author_operation_override or select_issues_rejects_invalid" -v`

Expected: FAIL because `selected_issue_operations_json` and `operation_by_issue` do not exist.

- [ ] **Step 3: Add the smallest backend contract and migration**

Define the canonical operations once in `schemas/generation.py` and add the request field:

```python
REVISION_OPERATIONS = (
    "naturalize", "tighten", "clarify", "voice_align",
    "ground_detail", "rhythm_adjust", "diction_refine",
    "project_style_align",
)


class SelectIssuesRequest(BaseModel):
    issue_ids: list[str] = Field(min_length=1)
    operation_by_issue: dict[str, str] = Field(default_factory=dict)
```

Add a nullable model field, create revision `b9c5d75f8a31` with parent `e23740fe6a52`, and use this migration body:

```python
def upgrade() -> None:
    op.add_column(
        "generation_steps",
        sa.Column("selected_issue_operations_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_steps", "selected_issue_operations_json")
```

Change the router to call:

```python
await svc.select_critic_issues(run_id, data.issue_ids, data.operation_by_issue)
```

In `GenerationService.select_critic_issues`, parse the selected Critic JSON, validate that all selected IDs exist, validate every mapping key belongs to `issue_ids`, reject values outside `REVISION_OPERATIONS`, derive missing values from each issue's `recommended_operation`, and save both JSON fields. Use `bad_request` codes `ISSUE_NOT_FOUND`, `ISSUE_OPERATION_NOT_SELECTED`, `INVALID_REVISION_OPERATION`, and `CRITIC_OPERATION_MISSING`.

Add a legal `recommended_operation` to every issue returned by `MockClient`'s Critic response: use `tighten` for `I01`, `ground_detail` for `I02`, `ground_detail` for `I03`, `tighten` for `I04`, and `rhythm_adjust` for `I05`.

- [ ] **Step 4: Run the focused API tests and verify GREEN**

Run: `cd apps/api && .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k "select_issues_uses_critic_recommendation or select_issues_persists_author_operation_override or select_issues_rejects_invalid" -v`

Expected: PASS with three tests collected and zero failures.

- [ ] **Step 5: Commit the persistence contract**

```powershell
git add apps/api/app/schemas/generation.py apps/api/app/models/generation.py apps/api/app/services/generation_service.py apps/api/app/routers/runs.py apps/api/app/llm/mock.py apps/api/alembic/versions/b9c5d75f8a31_add_selected_issue_operations.py apps/api/tests/test_runs_api.py
git commit -m "feat: persist revision operation choices"
```

### Task 2: 将完整问题和操作注入 Reviser，并更新默认提示词

**Files:**
- Modify: `apps/api/app/services/generation_service.py`
- Modify: `apps/api/app/prompts/defaults.py`
- Test: `apps/api/tests/test_runs_api.py`

**Interfaces:**
- Consumes: Task 1 的 `selected_issue_operations_json` 和 `REVISION_OPERATIONS`。
- Produces: Reviser 的 `{{selected_issues}}` 为完整 Critic 问题数组，每项带 `selected_operation`。
- Produces: Critic 默认输出要求 `recommended_operation`，Reviser 默认提示词定义八种操作的边界。

- [ ] **Step 1: Write failing context-propagation and Mock workflow tests**

Add a test that selects `I01` with `voice_align`, previews the Reviser stage, then asserts only `I01` appears and the rendered prompt carries both the issue information and final operation.

```python
@pytest.mark.asyncio
async def test_reviser_context_contains_selected_issue_and_author_operation(api_client):
    run_id = await _run_to_selected_critic(api_client)
    selected = await api_client.post(
        f"/api/runs/{run_id}/critic/select-issues",
        json={
            "issue_ids": ["I01"],
            "operation_by_issue": {"I01": "voice_align"},
        },
    )
    assert selected.status_code == 200

    preview = await api_client.post(f"/api/runs/{run_id}/steps/reviser/preview", json={})
    assert preview.status_code == 200
    prompt = preview.json()["rendered_user_prompt"]
    assert '"issue_id": "I01"' in prompt
    assert '"selected_operation": "voice_align"' in prompt
    assert '"issue_id": "I02"' not in prompt
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd apps/api && .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k "reviser_context_contains_selected_issue" -v`

Expected: FAIL because context still serialises only selected issue IDs.

- [ ] **Step 3: Implement minimal context and prompt changes**

In `_build_context_request`, when loading the selected Critic candidate for the Reviser stage:

```python
critic_data = json.loads(prev_candidate.parsed_output_json)
selected_ids = json.loads(prev_step.selected_issue_ids_json or "[]")
operation_by_issue = json.loads(prev_step.selected_issue_operations_json or "{}")
issues_by_id = {issue.get("issue_id"): issue for issue in critic_data.get("issues", [])}
ctx_req.selected_issues = [
    {**issues_by_id[issue_id], "selected_operation": operation_by_issue[issue_id]}
    for issue_id in selected_ids
    if issue_id in issues_by_id and issue_id in operation_by_issue
]
```

Keep `ctx_req.critic_report` as the complete report for traceability.

Update Critic's output contract to require `recommended_operation`, enumerate the eight allowed values, and require the selection to match the concrete problem rather than applying `ground_detail` by default.

Append a concise operation dispatch section to the Reviser system prompt. It must state that each selected issue is repaired only through its `selected_operation`, and include the exact constraints from the approved design for all eight operations. Keep the existing 80% preservation and patch output contract unchanged.

- [ ] **Step 4: Run focused tests and the existing five-stage test**

Run: `cd apps/api && .\venv\Scripts\python.exe -m pytest tests/test_runs_api.py -k "reviser_context_contains_selected_issue or full_five_stage_workflow" -v`

Expected: PASS with context proving only selected issues reach Reviser and with the Mock workflow completing all five stages.

- [ ] **Step 5: Commit context and prompt behaviour**

```powershell
git add apps/api/app/services/generation_service.py apps/api/app/prompts/defaults.py apps/api/tests/test_runs_api.py
git commit -m "feat: apply selected revision operations in reviser"
```

### Task 3: 为 Critic 问题提供可改选的操作界面

**Files:**
- Modify: `apps/web/src/types/generation.ts`
- Modify: `apps/web/src/api/runs.ts`
- Modify: `apps/web/src/features/generation/StagePanel.tsx`
- Create: `apps/web/src/features/generation/StagePanel.test.tsx`

**Interfaces:**
- Consumes: API request `{ issue_ids: string[], operation_by_issue: Record<string, RevisionOperation> }`。
- Produces: 作者可见的中文操作标签和每个已选择问题的操作映射。
- Depends on: Task 1 API field names and Task 2 Critic output field `recommended_operation`。

- [ ] **Step 1: Write the failing component tests**

Mock `listProviders` and `runsApi.selectIssues`; render `StagePanel` with a selected Critic candidate containing two issues. Verify the first issue defaults to Critic 建议，作者改变下拉框后点击确认会发送正确载荷。

```tsx
it('submits the author-selected operation for each selected critic issue', async () => {
  const selectIssues = vi.spyOn(runsApi, 'selectIssues').mockResolvedValue({ status: 'ok' })
  render(<StagePanel runId="run-1" stage="critic" step={criticStepWithOperations} />)

  await userEvent.click(screen.getByLabelText('选择 I01'))
  await userEvent.selectOptions(screen.getByLabelText('修订操作 I01'), 'voice_align')
  await userEvent.click(screen.getByRole('button', { name: '确认问题' }))

  expect(selectIssues).toHaveBeenCalledWith('run-1', {
    issue_ids: ['I01'],
    operation_by_issue: { I01: 'voice_align' },
  })
})

it('initialises a selected issue from the critic recommendation', async () => {
  render(<StagePanel runId="run-1" stage="critic" step={criticStepWithOperations} />)
  await userEvent.click(screen.getByLabelText('选择 I01'))
  expect(screen.getByLabelText('修订操作 I01')).toHaveValue('tighten')
})
```

- [ ] **Step 2: Run the component test and verify RED**

Run: `cd apps/web && npx vitest run src/features/generation/StagePanel.test.tsx`

Expected: FAIL because the operation types, select controls and request mapping do not exist.

- [ ] **Step 3: Implement the narrow UI contract**

Add TypeScript declarations:

```ts
export const REVISION_OPERATIONS = [
  'naturalize', 'tighten', 'clarify', 'voice_align',
  'ground_detail', 'rhythm_adjust', 'diction_refine',
  'project_style_align',
] as const

export type RevisionOperation = (typeof REVISION_OPERATIONS)[number]

export interface CriticIssue {
  issue_id: string
  problem: string
  recommended_operation: RevisionOperation
}

export interface SelectIssues {
  issue_ids: string[]
  operation_by_issue?: Record<string, RevisionOperation>
}
```

In `StagePanel`, replace the string-only issue parser with one that safely reads `recommended_operation`. For valid Critic issues, render a checkbox with `aria-label="选择 {issue_id}"`, a labelled `<select aria-label="修订操作 {issue_id}">`, and Chinese labels:

```ts
const REVISION_OPERATION_LABELS: Record<RevisionOperation, string> = {
  naturalize: '自然化', tighten: '删冗聚焦', clarify: '信息清理',
  voice_align: '角色语气', ground_detail: '补足有效细节',
  rhythm_adjust: '节奏校准', diction_refine: '用词校准',
  project_style_align: '项目文风对齐',
}
```

Maintain `selectedIssues: Set<string>` and `operationByIssue: Record<string, RevisionOperation>`. Selecting a checkbox initialises its mapping from `recommended_operation`; clearing a checkbox deletes it. On candidate identity change, reset both state containers. Submit only mappings for checked IDs.

- [ ] **Step 4: Run focused front-end tests and verify GREEN**

Run: `cd apps/web && npx vitest run src/features/generation/StagePanel.test.tsx`

Expected: PASS with both tests green.

- [ ] **Step 5: Commit the author controls**

```powershell
git add apps/web/src/types/generation.ts apps/web/src/api/runs.ts apps/web/src/features/generation/StagePanel.tsx apps/web/src/features/generation/StagePanel.test.tsx
git commit -m "feat: let authors choose revision operations"
```

### Task 4: 完整本地与真实 LLM 验收

**Files:**
- Modify: `README.md` only if a command or user-visible behaviour differs from the documented workflow.
- Test: `apps/api/tests/`, `apps/web/src/features/generation/StagePanel.test.tsx`, `apps/web/tests/`, `apps/web/e2e/`.

**Interfaces:**
- Consumes: 完成后的 API、提示词、Mock 与前端操作选择。
- Produces: 本地命令输出和一次真实非 Mock 五阶段调用的验收记录（不保存密钥）。

- [ ] **Step 1: Run backend verification**

Run:

```powershell
cd apps/api
.\venv\Scripts\python.exe -m pytest -v
.\venv\Scripts\alembic.exe upgrade head
```

Expected: all pytest tests pass and Alembic upgrades the local database without an error.

- [ ] **Step 2: Run frontend verification**

Run:

```powershell
cd apps/web
npm run lint
npx vitest run
npm run build
```

Expected: ESLint exits 0, all Vitest tests pass, and the Vite production build exits 0.

- [ ] **Step 3: Run existing Playwright coverage**

Start the local API and Vite server through the project script, then run:

```powershell
cd apps/web
npm run e2e
```

Expected: the existing browser suite exits 0. Stop only the processes started for this check.

- [ ] **Step 4: Discover a usable local non-Mock provider without exposing secrets**

Use the local Providers API or database service to list only provider IDs, names, enabled state and provider type. Select an enabled non-`mock` provider and one configured model. Never print `api_key_encrypted`, decrypted API keys or full provider configuration.

Expected: a usable non-Mock provider and model are identified; otherwise record `REAL_LLM_VALIDATION_BLOCKED` with the non-sensitive reason and do not claim real LLM validation passed.

- [ ] **Step 5: Execute one real five-stage acceptance scenario**

Create a temporary local project and short chapter with this bounded campus scenario:

```text
早读前，班长沈溪核对名单，陈默只想回座位补觉。
名单少了一名学生；沈溪不知道陈默认识这个名字。
本章只让陈默决定暂时留下，不能确认恋爱关系。
```

For Planner, Writer, Critic, Reviser and Judge set the discovered non-Mock provider/model and conservative limits: Planner 700 tokens, Writer 1,600 tokens, Critic 900 tokens, Reviser 1,200 tokens, Judge 900 tokens. Select one Critic issue and deliberately override its recommendation to `voice_align` before executing Reviser.

Expected evidence:

```text
Critic: every emitted issue has a legal recommended_operation.
Reviser prompt: contains "selected_operation": "voice_align" for the selected issue.
Reviser: valid JSON with non-empty revised_text.
Judge: valid JSON with a decision.
```

Do not include raw prompts, chapter text, keys, or provider secret material in the final handoff. Delete the temporary project afterward only if it was created exclusively for validation and no user-authored content was added.

- [ ] **Step 6: Commit any required README update and inspect the final diff**

```powershell
git diff --check
git status --short
git add README.md  # only when README changed
git commit -m "docs: document revision operation controls"  # only when README changed
```

Expected: no whitespace errors and no unintended files outside the scoped feature.
