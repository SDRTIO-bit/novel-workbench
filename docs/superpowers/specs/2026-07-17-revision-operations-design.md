# 局部修订操作设计

## 目标

将八种受控的小说局部修订操作接入现有五步工作流：

`Planner → Writer → Critic → Reviser → Judge`

操作不是额外的 Agent，也不是对全文连续润色。Critic 为每个问题推荐一种操作，作者可逐项改选；Reviser 只对被选中的问题按指定操作定点修订。

## 范围

本次实现下列操作：

| 标识 | 名称 | 作用 |
| --- | --- | --- |
| `naturalize` | 自然化 | 删除机械完整、重复解释和过度对称表达；允许符合角色的停顿、找补和答非所问。 |
| `tighten` | 删冗聚焦 | 删除已由动作或对白表达的重复解释，以及与当前场景无关的装饰性内容。 |
| `clarify` | 信息清理 | 按角色观察与行动重排信息，移除越出当前视角认知的信息。 |
| `voice_align` | 角色语气校准 | 让指定对白符合角色身份、目的、关系和当下压力。 |
| `ground_detail` | 有效细节补足 | 只补充支撑事件理解的物件、空间或感官细节。 |
| `rhythm_adjust` | 节奏校准 | 调整机械重复的句群结构，令句式服从事件节奏。 |
| `diction_refine` | 用词校准 | 修正含糊、失真、重复或不符合人物认知的用词。 |
| `project_style_align` | 项目文风对齐 | 参考项目认可样章的叙述距离、段落和描写密度，不复刻具体句子或意象。 |

不在本次范围：独立的操作提示词管理页、自动多轮修订、全文润色、增加第六个 Agent、自动学习作者偏好。

## 方案选择

选择“操作作为 Critic 问题属性”的方案。

备选方案一是将八个操作做成八个串行润色步骤，会反复覆盖文本并造成过度打磨。备选方案二是为操作建立独立的可视化工作流和提示词实体，灵活但会扩大 MVP 的数据模型与界面范围。

本方案复用现有的 Critic、问题选择、Reviser 与提示词版本机制；每次问题只执行一项主要操作，作者能在界面中改选。

## 数据与 API 合同

### Critic 输出

每个 `issues[]` 项新增必填字段：

```json
{
  "issue_id": "I01",
  "issue_type": "show_vs_tell",
  "paragraph_ids": [3],
  "problem": "旁白重复解释了对白已经传达的尴尬。",
  "revision_goal": "删除重复解释，保留现场证据。",
  "recommended_operation": "tighten"
}
```

`recommended_operation` 必须是八种操作标识之一。

### 作者选择

现有请求保留 `issue_ids`，以兼容 MCP 与既有调用；新增可选映射：

```json
{
  "issue_ids": ["I01", "I03"],
  "operation_by_issue": {
    "I01": "tighten",
    "I03": "voice_align"
  }
}
```

未提供映射的已选问题使用 Critic 的 `recommended_operation`。

`GenerationStep` 新增 `selected_issue_operations_json`，仅保存已选问题的最终操作映射；既有 `selected_issue_ids_json` 继续保存问题 ID 列表。

### Reviser 上下文

构造 Reviser 上下文时，系统从已选择的 Critic 报告中提取完整问题对象，并添加：

```json
{
  "selected_operation": "tighten"
}
```

因此 `{{selected_issues}}` 同时包含问题位置、问题描述、修改目标、Critic 推荐和作者最终选择。Reviser 不从问题 ID 推测修改内容。

## 提示词行为

Critic 默认提示词将：

- 为每个问题选择一个推荐操作；
- 不把“丰富细节”作为默认修法，只有现场理解确实缺信息时才选择 `ground_detail`；
- 保持最多五个问题和保护段落约束。

Reviser 默认提示词将保留现有的定点修订限制，并增加：

- 不改变剧情事实、信息边界、关系阶段、叙事视角与场景结果；
- 不修改 `protected_strengths`；
- 不新增人物、设定、伏笔、无依据的心理结论或通用微动作；
- 每个问题按其 `selected_operation` 的专属边界执行；
- 粗糙但有角色声音的表达，不得仅因不够工整而修改。

八种操作规则写入默认 Reviser 提示词，提示词版本仍可在既有提示词中心编辑、复制和回滚。本次不创建独立的操作提示词配置界面。

## 前端行为

Critic 候选的每个问题显示：问题描述、推荐操作、操作选择器和勾选框。

- 勾选时默认采用推荐操作；
- 作者可在八种操作中切换；
- 提交时发送已选问题与每项最终操作；
- 未选择的问题不发送给 Reviser；
- 候选切换或下游过期时，操作选择随当前 Critic 候选重新初始化，避免将旧候选的问题映射带入新候选。

既有候选、下游 stale、手动最终采用与 Judge 界面不改变。

## 错误处理与兼容性

- 后端拒绝未知操作、未出现在当前 Critic 报告中的问题 ID，以及为未选中问题提交的操作映射。
- 旧调用只传 `issue_ids` 时自动采用 Critic 推荐，维持兼容。
- Critic 候选缺少或给出非法 `recommended_operation` 时，该候选不能用于问题选择，并返回明确的结构化输出错误。
- 旧数据库迁移后，历史步骤的操作映射为空；历史运行仍可查看，只有新的 Critic 结果会提供操作。

## 测试与验收

### 自动化验证

新增或调整测试覆盖：

1. Critic 输出的推荐操作被接受，非法操作被拒绝；
2. 只传 `issue_ids` 时后端采用 Critic 默认推荐；
3. 作者覆盖推荐操作后，完整问题及最终操作进入 Reviser 渲染上下文；
4. 未选问题不进入 Reviser 上下文；
5. Mock Provider 为每个 Critic 问题返回合法操作，完整五阶段流程仍通过；
6. 前端显示推荐值、允许改选，并向 API 发送映射。

完成后运行后端 pytest、前端 Vitest、ESLint、TypeScript/Vite 构建，以及现有 Playwright 端到端检查。

### 真实 LLM 验收

使用本机已配置的非 Mock 服务商创建临时校园场景项目，限制五步输出长度，并完整执行：

`Planner → Writer → Critic → 选择/覆盖操作 → Reviser → Judge`

验收证据包括：

1. Critic 每个问题均返回合法 `recommended_operation`；
2. 作者覆盖的操作实际出现在 Reviser 渲染提示词中；
3. Reviser 返回有效 JSON、补丁与非空修订稿；
4. Judge 返回有效 JSON 与决策；
5. 不打印 API Key、原始密钥或敏感 Provider 配置。

若本机未配置可用的非 Mock 服务商或其连接失败，自动化检查仍完成，但真实 LLM 验收明确记录为受外部配置阻塞，不能声称已通过。
