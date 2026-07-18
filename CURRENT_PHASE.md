# Current Phase

## 项目主线

通过固定管线提高小说正文质量：

Planner
→ Writer
→ Critic
→ Reviser
→ Judge

核心叙事目标：

有限证据
→ 人物判断
→ 存在其他可能
→ 人物选择
→ 代价或承诺
→ 选择专属后果
→ 新行动限制
→ 停在可见事实

## 当前阶段

F2 已通过（含 Judge 重新执行）。Judge 给出 `accept_merged` 决策（细节见下方），不自动接受 Judge 结论，等用户裁决。

## 当前代码

branch:
integration/tgbreak-writer-adapter

commit:
3fbecf61566795f55aafe36163178d4d75e125e7

## Judge 运行时备注

- Judge 重新执行未通过 8766 端口的 API，而是直接调用 `GenerationService.execute_stage(run_id, "judge", {})`。
  原因：监听 8766 的 uvicorn 来自主仓 `E:\3\novel-workbench\apps\api`（其 `IssueStatus` 仍缺 `partially_resolved`），并且其 `NW_DATA_DIR` 指向的不是 `planner-builtin-writer-d.db`；两个原因叠加，API 调用会再次复现原枚举错误。
- 实际跑通的执行通过以下环境绕过两个问题：
  1. `sys.path` 注入 worktree 的 `apps/api`，让 `app.*` 加载 worktree 代码（含枚举修复）。
  2. `DATABASE_URL=sqlite+aiosqlite:///E:\3\novel-workbench\.local\experiments\planner-builtin-writer-d.db` 指到目标 DB；
     `NW_DATA_DIR=E:\3\novel-workbench\data` 让 `secret_key_path` 解析为 `data/.secret_key`，该 key 与 2026-07-16 加密 DeepSeek key 时使用的 key 一致。
- 没有修改任何 prompt 或 schema；仅消费已存在的 `IssueStatus.partially_resolved` 值。

## 当前数据库

E:\3\novel-workbench\.local\experiments\planner-builtin-writer-d.db

## 已选 Planner

Candidate:
d9d44c85-72dd-4766-a007-1f64adb867c3

## 已选 Writer

Candidate:
ee2c90be-a734-4a76-a119-92a5139f470e

结论：

- 正文简洁。
- 没有新增外部剧情。
- 没有停止后的环境余韵。
- 未精确完成鼻尖接触。
- rejected alternative、cost/commitment、next constraint 不完整。

## 已通过 Critic

Candidate:
96067381-b2ef-40a6-99d3-fc9441eef24c

PromptVersion:
981bd585-b78b-4b14-9cda-33ac0d862fa8

状态：
通过，允许进入 Reviser。

Critic正确识别：

- "几乎碰到"与 Planner 的实际接触矛盾。
- rejected alternative 缺失。
- cost_or_commitment 缺失。
- next_constraint 缺失。
- "她没有缩回手"应保留。

Critic Prompt 和 Candidate 冻结，不再修改。

## 已失败 Reviser

Candidate:
f6d9c1a6-bdda-4ade-a277-1758b612b248

失败原因：

新增 Planner 和原稿均未规定的动作：

"小满的手没有缩回去，反而轻轻张开，让那只猫蹭过她的指尖。"

其中：

- "轻轻张开"是新增动作。
- "蹭过她的指尖"是新增接触结果。
- Planner 只要求鼻尖碰到手背且小满没有缩回。

该 Candidate 不选择，不进入 Judge。

## Reviser Fact Closure v1

PromptVersion:
a5fb8a7d-c9de-49b2-8d82-0f98d0edd04f

Base PromptVersion:
b3dbe0b6-1963-4c22-a3d0-38d4d353fcd8

## 新 Reviser Candidate

Candidate:
f0bc2da6-0d8d-463b-8e2d-279819da7692

状态：
F2_PASSED，已选择。

执行结果：
- input_tokens: 4657
- output_tokens: 1080
- finish_reason: stop
- latency_ms: 8209
- unchanged_ratio: 0.90

修订内容：
- 删除"动作比平时更慢一些，像在等什么慢慢落定"（I02）。
- 增加"门外的天色又暗了一层"体现时间代价（I04）。
- 将"几乎要碰到她的指背"改为"轻轻碰到她的手背"（I01/I05）。
- 保留"她没有缩回手"。

## F2 确定性门检查

| 门 | 结果 | 证据 |
|---|---|---|
| Gate 1 精确停止事实 | PASS | "猫的鼻尖仰起，轻轻碰到她的手背。她没有缩回手。" |
| Gate 2 无新接触动作 | PASS | 无张开手、抚摸、蹭过指尖、舔手、手指移动、反手触碰、第二次接触 |
| Gate 3 事实来源审计 | PASS | 新增事实仅2处：天色变暗（Planner时间/压力）、鼻尖碰手背（Planner stop_state） |
| Gate 4 Critic问题处理 | PASS | stop_state已修复；cost以天色变暗呈现；"她没有缩回手"保留 |
| Gate 5 保留原文 | PASS | unchanged_ratio = 0.90 >= 0.80 |
| Gate 6 结尾位置 | PASS | 接触事实后正文立即结束，无后续叙事段落 |

## Judge

IssueStatus 枚举已在 `apps/api/app/llm/output_contracts.py` 加入 `partially_resolved`（line 160），Judge 合同解析路径已对齐新枚举。

### Attempt 1（原始失败，保留作历史）

Candidate:
66dbcdb0-0fb8-4d69-ae4e-f48a576b44d3

错误：
JUDGE_OUTPUT_CONTRACT_INVALID: issue_results.3.status 输入值 'partially_resolved' 不在允许的枚举值 ['resolved', 'unresolved', 'revision_worse'] 中。

### Attempt 4（重新执行，成功）

Candidate:
84badbbf-042e-450a-b2c0-c44dec0e7af1

执行环境：
- 代码：`E:\3\novel-workbench\.worktrees\tgbreak-writer-adapter\apps\api`（worktree，含枚举修复）
- 数据库：`E:\3\novel-workbench\.local\experiments\planner-builtin-writer-d.db`
- 加密密钥：`E:\3\novel-workbench\data\.secret_key`（`.local/experiments/.secret_key` 在 2026-07-19 03:55 被重写，与 2026-07-16 加密的 DeepSeek key 不匹配；恢复使用主仓 `data/.secret_key` 即可解密）
- 调用：直接调用 `GenerationService.execute_stage(run_id, "judge", {})` 一次

执行结果：
- provider: 34c14b6b-7231-432a-96b2-8272329b828d（DeepSeek）
- model: deepseek-chat
- prompt_version: 9f5fa364-15ee-436e-80ef-ed5087e840e3
- input_tokens: 5690
- output_tokens: 1043
- finish_reason: stop
- latency_ms: 7987
- reasoning_tokens: null
- error_code: null
- contract_parsed_ok: true
- raw_response 前 500 字符：`{\n  "decision": "accept_merged",\n  "issue_results": [\n    {\n      "issue_id": "I01",\n      "status": "resolved",\n      "action": "keep_revision",\n      "comment": "修订稿中猫的鼻尖碰到手背，stop_state可见事实已实现。"\n    },\n    {\n      "issue_id": "I02",\n      "status": "resolved",\n      "action": "keep_revision",\n      "comment": "删除了'像在等什么慢慢落定'，不再替读者推断。"\n    },\n    {\n      "issue_id": "I03",\n      "status": "unresolved",\n      "action": "restore_original",\n      "comment": "修订稿未增加替代路线或新约束的可见表现。"\n    },\n    {\n`

Parsed output 摘要：
- decision: **accept_merged**（不直接采纳 revision，也不直接采纳 original，而是请求合并：I03 在原文中更接近满足，I01/I02/I04/I05 在 revision 中更接近满足）
- issue_results: 5
  - I01: resolved / keep_revision（stop_state 可见事实已实现）
  - I02: resolved / keep_revision（删除推断句）
  - I03: unresolved / restore_original（替代路线/代价/承诺仍不足）
  - I04: resolved / keep_revision（增加天色变暗，体现时间代价）
  - I05: resolved / keep_revision（实际接触已修复）
- new_problems: 0
- revision_became_cleaner_but_flatter: false
- author_intent_preserved: true
- chapter_contract_completed: true
- main_payoff_preserved: true
- reader_inference_preserved: true
- decision_consequence_preserved: true
- narrator_management_reduced: true
- necessary_information_lost: false
- quality_score: 88
- state_patch:
  - facts_added: ["小满进入了书店，手背被阿橘碰到后没有缩回。"]
  - relationships_changed: ["老陈与小满之间建立了初步的无声信任。"]
  - threads_carry_forward: ["小满的迷路原因和家庭背景仍未揭示。"]
- causal_transition_results: CT01 original=fail, revision=pass, preferred_version=manual_review（成本与新约束不够明显，但证据与行动链完整）
- final_text: 642 字符（非空，accept_merged 必需字段已满足）

contract 解析结果：成功。`validate_stage_output("judge", ...)` 与 `validate_judge_output_for_selected_issues(...)` 均通过，step.status 由 failed 变为 completed。

decision 是否建议接受 revision：部分。
- I01/I02/I04/I05：建议 keep_revision
- I03：建议 restore_original
- 最终裁决是 accept_merged（按 I03 选择原文片段，按其他 issue 选择 revision 片段）
- 严格意义上 Judge 没有"整段接受 revision"；它推荐了一种按 issue 拆分的合并方案

### 中间产物说明（attempts 2 / 3）

`rerun_judge` 在确认密钥问题前两次进入 `execute_stage`，分别写入了 attempt 2（`7e92641b-…`）和 attempt 3（`98bf2263-…`），均因 Fernet `InvalidToken`（`.local/experiments/.secret_key` 不匹配）抛出 `LLM_ERROR`，input_tokens=0、output_tokens=0。它们是排查密钥的副产物，不包含有效输出，**不参与 Judge 结论**。最终生效的仅 attempt 4。

### 结论

不自动接受 Judge 结论，不覆盖原文。等待用户裁决：
- 选项 A：按 `accept_merged` 调用 `accept_final_text(accept_type=accept_merged, final_text=...)`，写入 chapter 版本。
- 选项 B：忽略 I03 的 restore_original，按 I01/I02/I04/I05 全部 keep_revision 接受 revision。
- 选项 C：以 `manual_review` 介入，逐 issue 决定。

## 管线完整闭环

五阶段管线已跑通一次完整闭环：

```text
Planner → Writer → Critic → Reviser → Judge
  ✓        ✓        ✓        ✓        ✓
```

关键发现：

1. Critic Planner Contract v1 能正确将 Planner 视为合同逐项核验。
2. Reviser Fact Closure v1 的事实闭包规则有效阻止了新增动作。
3. Judge 枚举兼容性已修复（`partially_resolved` 加入 `IssueStatus`），合同解析路径恢复通过。
4. Judge 给出 `accept_merged` 决策：I01/I02/I04/I05 接受 revision，I03 回到 original；CT01 preferred_version=manual_review，提示成本与新约束仍不够明显。

## 下一步选项

1. 按 Judge `accept_merged` 落稿（按 issue 拆分合并，I03 取原文片段，其他取 revision 片段）。
2. 忽略 I03 仍按 revision 落稿（更接近 `accept_revision`）。
3. 介入 `manual_review`，逐 issue 决定，特别是 I03 与 CT01 的成本/约束。
4. 结束本轮实验，记录成果。

## 禁止事项

- 不修改 Planner。
- 不修改 Writer。
- 不修改已通过的 Critic。
- 不修改已通过的 Reviser。
- 不修改工作流结构。
- 不新增 Stage 或 Agent。
- 不调用 TGbreak。
