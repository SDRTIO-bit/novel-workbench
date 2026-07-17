# 因果转折写作管线设计与实施交接

## 0. 文档状态

- 状态：设计已确认，等待实现
- 设计日期：2026-07-17
- 目标仓库：`E:\3\novel-workbench`
- 目标分支：`main`
- 设计时基线提交：`5df99ef`
- 当前工作流：`Planner → Writer → Critic → Reviser → Judge`
- 实施约束：不增加第六个 Agent，不用检测器自动循环改稿，不覆盖用户已有提示词版本
- 本文用途：交给另一名 Coding Agent 后，应能在不依赖本次聊天记录的情况下完成实现、测试和真实 LLM 验收

> 交接提醒：设计时工作区已有用户状态 `D data/chapters/.gitkeep`。它不是本功能的一部分，实现者不得恢复、暂存或提交该变更，除非用户另行要求。

## 1. 背景与问题定义

项目已经具备完整五步写作流、提示词版本、多模型路由、候选保留、定点修订、Judge 验收和本地章节保存。当前问题不是工作流无法运行，而是生成文本经外部检测后，大部分段落被判为“疑似 AI”。

同一章的两个局部片段出现了较明显的“人工特征”，但它们不是同一种表面写法。

### 1.1 线索片段

结构如下：

```text
人物执行普通维修操作
→ 意外看到编号 GR-0713
→ 最小反应：“他顿了一下”
→ 并列给出工单编号
→ 人物改变提问：“你爸叫什么？”
```

文本没有替读者明确说明“两个编号一致，也许与女孩父亲有关”。读者通过可见证据和人物下一步行动自行完成连接。

### 1.2 救援片段

外部检测的人工区间并未从承重参数开始，而是从命令“松手，我拉你回来”开始。结构如下：

```text
约束已经建立
→ 人物给出指令
→ 另一人物作出不可撤销的选择
→ 选择立即产生物理后果
→ 后果制造新的约束
→ 人物继续处理新约束
```

因此，精确数字、专业术语、短句本身都不是稳定原因。更可信的共同特征是：叙述者没有预先总结行动方案，也没有在结果发生后替读者解释场景意义；局部事实直接迫使人物改变下一步。

### 1.3 当前管线为何容易丢失这种特征

当前默认提示词存在四个结构性缺口：

1. Planner 只规划场景目标、压力、转折点和结束条件，没有规划“什么事实出现后，人物必须改变什么行动，以及哪些推论必须留给读者”。
2. Writer 接受的是宏观章节契约，并被要求完整完成开场、发展、爽点和结尾钩子，模型容易主动补齐推理、方案和意义。
3. Critic 只有泛化的 `show_vs_tell`、`exposition_clumsy` 等类型，无法区分“证据后抢答”“行动前先总结方案”“参数没有转成选择”等不同问题。
4. Judge 重视契约完整与文字质量，但没有显式检查读者推理空间、决定—后果链和叙述者管理痕迹。

此外，`apps/api/app/llm/parser.py` 当前只保证返回值是 JSON 对象，并未按阶段严格校验 Planner、Critic、Reviser、Judge 的完整字段合同。新增结构若只依赖提示词约定，错误会延迟到下游暴露。

## 2. 目标

本功能要让五步管线能够规划、生成、诊断、修复并保护以下两类因果转折：

1. **证据到行动**：证据可见，结论不明说，人物下一步因证据而改变。
2. **约束到选择**：约束可见，人物作出选择，选择产生后果，后果形成新约束。

具体成功标准：

- Writer 不再依赖抽象的“降低 AI 感”指令，而是执行 Planner 输出的局部因果合同。
- Critic 能准确定位作者抢答、行动预告、技术说明悬空和结果重复总结。
- Reviser 能删除显式解释而不删除必要证据，也能把“先讲方案再执行”改成选择—后果链。
- Judge 能拒绝“更流畅但更平”“留白后逻辑断裂”的修订。
- 外部检测结果可与具体候选、段落和因果转折关联，便于做同模型、同参数的长期 A/B 比较。
- 所有变化保持现有五阶段架构、候选机制、上下文预览、下游 stale 和最终采用行为。

## 3. 非目标

本次明确不做：

- 不增加独立“降 AI”Agent 或第六个生成阶段。
- 不接入外部检测器自动循环重写。
- 不把“人工率”作为模型可见的硬奖励。
- 不通过故意错字、残句、网络词、随机标点或无意义口语伪造人工特征。
- 不要求每个场景都使用两类因果转折。
- 不为此功能引入向量数据库、长期记忆或自动提示词学习。
- 不重构与本功能无关的项目、章节、Provider、导入导出和 MCP 架构。
- 不以外部检测结果替代小说连贯性、人物逻辑和阅读质量验收。

## 4. 方案选择

### 4.1 采用方案：结构化因果转折 + 外部检测反馈记录

在 Planner 输出中增加少量 `causal_transitions`。Writer 根据转折合同写正文；Critic 对每张转折卡做结构审计；Reviser 提供两个专用定点操作；Judge 对比修订前后是否保留推理空间和因果链。Judge 之后允许作者记录外部检测结果，但检测器不进入自动生成回路。

这是推荐方案，因为它改变的是“文本为什么往下走”，而不是词汇表面，同时可以被现有五步架构直接承载。

### 4.2 未采用：只修改 Writer 提示词

优点是快，缺点是不可观测、不可诊断，也无法让 Reviser 和 Judge 保护成功片段。模型仍可能把“不要解释”机械化成短句、留白和分镜体。

### 4.3 未采用：检测器闭环优化

即每次生成后调用检测器，根据分数继续改稿。该方案会快速过拟合检测器的分段和统计偏好，可能牺牲小说质量；当前检测器也未确认具备稳定 API。外部检测只作为实验反馈保存，不直接指导单次自动改写。

## 5. 总体数据流

```text
章节契约 + 项目资料
        ↓
Planner：生成场景规划和 0—3 张因果转折卡
        ↓
Writer：呈现 trigger，执行 next_action，隐藏 reader_inference
        ↓
Critic：逐卡审计 + 常规章节问题诊断 + 保护成功段落
        ↓
作者选择问题与修订操作
        ↓
Reviser：withhold_inference / causalize 或既有八种操作
        ↓
Judge：比较推理空间、选择—后果链、信息完整性和文本活力
        ↓
作者采用最终文本
        ↓
可选：录入外部检测比例与人工区间，关联候选和转折卡
```

## 6. 核心数据合同

### 6.1 Planner 新增 `causal_transitions`

Planner 顶层 JSON 新增必填数组 `causal_transitions`。数组允许为空，最多 3 项。不得为了满足结构强行制造转折。

```json
{
  "scene_goal": "陆衡确认异常工单与许栀父亲之间存在待查联系，并处理重力故障",
  "location": "旧商业区悬空步道",
  "time": "2196年11月7日23:47至零点后",
  "characters": [],
  "pressure": "重力节点即将失效",
  "turning_point": "陆衡从例行维护转为主动追查",
  "end_condition": "异常工单留下无法解释的未来时间戳",
  "forbidden": [],
  "causal_transitions": [
    {
      "id": "CT01",
      "kind": "evidence_to_action",
      "visible_trigger": "接线盒标签出现 GR-0713",
      "character_next_action": "陆衡询问许栀父亲的名字",
      "reader_must_infer": "标签、未来工单和许栀父亲之间可能存在联系",
      "narrator_must_not_state": [
        "两个编号一致",
        "这意味着许栀父亲与未来工单有关"
      ],
      "immediate_consequence": "陆衡不再把许栀当成普通闯入者",
      "next_constraint": "陆衡不能向许栀透露未来工单"
    },
    {
      "id": "CT02",
      "kind": "constraint_to_choice",
      "visible_trigger": "缆绳和磁力扣能够承受两人重量",
      "character_next_action": "陆衡要求许栀松手",
      "reader_must_infer": "陆衡已完成承重与轨迹判断",
      "narrator_must_not_state": [
        "陆衡判断了两件事",
        "这是唯一可行的方案"
      ],
      "immediate_consequence": "许栀松手，被缆绳张力拉向陆衡",
      "next_constraint": "两人仍需在重力恢复前固定身体"
    }
  ],
  "chapter_contract_check": {}
}
```

字段约束：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | string | 当前 Planner 输出内唯一，格式 `CT01`、`CT02`、`CT03` |
| `kind` | enum | `evidence_to_action` 或 `constraint_to_choice` |
| `visible_trigger` | string | 正文中可被当前视角观察到的事实或约束，不得是抽象主题 |
| `character_next_action` | string | 人物在 trigger 后实际改变的提问、指令、选择或行动 |
| `reader_must_infer` | string | 读者根据证据和行动自行得到、正文不直接宣告的连接 |
| `narrator_must_not_state` | string[] | 禁止叙述者直接写出的结论或方案总结；至少 1 项 |
| `immediate_consequence` | string | next_action 在当前场景中产生的可见结果 |
| `next_constraint` | string | 结果之后仍需处理的新限制；不得直接把冲突全部解决 |

语义约束：

- `evidence_to_action` 的 trigger 必须是信息或证据，next_action 必须体现人物因信息改变行动。
- `constraint_to_choice` 的 trigger 必须是实际限制，next_action 必须包含角色选择或指令。
- `reader_must_infer` 不能是项目中尚无依据的新设定。
- `narrator_must_not_state` 是语义禁区，不要求正文进行逐字匹配；Critic 需识别同义解释。
- `immediate_consequence` 和 `next_constraint` 必须在本场景范围内可落地。
- 同一场景不应创建内容重复的转折卡。

### 6.2 Critic 新增问题类型

在既有 `issue_type` 枚举中增加：

| 标识 | 含义 |
| --- | --- |
| `inference_overexplained` | 证据足够，但叙述者或人物又明确说出本应由读者完成的结论 |
| `action_preannounced` | 行动发生前，旁白先完整总结方案、步骤或正确答案 |
| `technical_exposition_unconverted` | 技术参数或规则出现后，没有及时转成人物选择和后果 |
| `consequence_summarized` | 行动结果已可见，旁白又重复概括其意义或情绪结论 |
| `causal_transition_missing` | 新证据或新约束出现后，人物下一步没有受到影响 |

这些类型不替代 `show_vs_tell`。只有问题明确涉及因果转折时才使用新类型；一般性直述情绪仍用既有类型。

### 6.3 Critic 新增 `causal_transition_check`

Critic 顶层 JSON 新增必填数组，必须覆盖 Planner 中每个 `causal_transitions[].id`；Planner 数组为空时这里也为空。

```json
{
  "causal_transition_check": [
    {
      "transition_id": "CT01",
      "trigger_visible": true,
      "next_action_changed": true,
      "reader_inference_withheld": true,
      "forbidden_explanation_found": [],
      "consequence_visible": true,
      "next_constraint_preserved": true,
      "paragraph_ids": [21, 22, 23, 24, 25],
      "result": "pass",
      "comment": "编号并列出现后，陆衡直接改变提问，叙述者没有解释编号关系。"
    }
  ]
}
```

字段约束：

- `result`：`pass`、`fail` 或 `not_present`。
- `paragraph_ids`：覆盖该转折在正文中的最小连续范围。
- 任一布尔字段为 `false` 时，`result` 不得是 `pass`。
- `forbidden_explanation_found` 非空时，Critic 必须创建对应 issue，通常推荐 `withhold_inference`。
- Planner 转折未进入正文时使用 `not_present`，并创建 `causal_transition_missing` issue。

### 6.4 `protected_strengths` 扩展

每项增加可选 `strength_type`：

```text
reader_inference_gap
choice_consequence_chain
character_voice
scene_specific_detail
effective_roughness
```

因果转折审计为 `pass` 时，Critic 应将其段落加入 `protected_strengths`，类型分别为 `reader_inference_gap` 或 `choice_consequence_chain`。Reviser 不得修改这些段落，除非同一区间同时存在高严重度事实错误；出现冲突时应返回 `scene_rewrite` 或要求人工判断，而不是静默突破保护。

### 6.5 新增修订操作

在当前八种 `REVISION_OPERATIONS` 后增加：

```text
withhold_inference
causalize
```

#### `withhold_inference`

适用问题：`inference_overexplained`、部分 `consequence_summarized`。

行为合同：

```text
保留证据、当前视角能够观察到的事实、人物最小反应和后续行动。
删除或改写证据与结论之间的显式说明。
不得删除读者完成推理所必需的信息。
不得用模糊心理、故作神秘或刻意残句替代被删除的解释。
```

#### `causalize`

适用问题：`action_preannounced`、`technical_exposition_unconverted`、`causal_transition_missing`。

行为合同：

```text
删除行动前的方案总结或步骤清单。
把必要判断压缩进人物命令、选择、操作或带偏差的即时判断。
让选择产生可见后果，并保留后果制造的新约束。
不得新增事故，不得改变 Planner 规定的场景结果。
```

旧 Critic 候选没有新操作时继续按既有八种操作运行。API 不得强制历史记录迁移为新操作。

### 6.6 Judge 新增验收字段

Judge 顶层 JSON 新增：

```json
{
  "reader_inference_preserved": true,
  "decision_consequence_preserved": true,
  "narrator_management_reduced": true,
  "necessary_information_lost": false,
  "causal_transition_results": [
    {
      "transition_id": "CT01",
      "original_status": "pass",
      "revision_status": "pass",
      "preferred_version": "original",
      "comment": "修订没有改善已成功的推理留白，保留原段。"
    }
  ]
}
```

约束：

- `preferred_version`：`original`、`revision` 或 `manual_review`。
- 若 `necessary_information_lost` 为 `true`，不得 `accept_revision`。
- 若修订把成功的转折从 `pass` 降为 `fail`，相应 issue 必须 `revision_worse` 且建议 `restore_original`。
- 若修订只删除解释但导致 next_action 无依据，必须判为信息丢失或因果断裂。
- `revision_became_cleaner_but_flatter` 与新字段共同判断，不能因为句子更短、更顺就默认接受修订。

## 7. 提示词设计

### 7.1 Planner 默认提示词

新增职责：

```text
在真实存在局部因果转折时生成 1—3 张 causal_transitions；没有合适转折时输出空数组，不得凑数。

证据到行动：规划正文可见证据、人物因此改变的下一步，以及必须留给读者自行连接的推论。

约束到选择：规划现实限制、人物作出的选择或指令、立即后果和后果产生的新限制。

不得把 reader_must_infer 写成角色必然知道的正确答案；人物可以误判。
不得以抽象情绪或主题充当 visible_trigger、immediate_consequence 或 next_constraint。
```

Planner 的 `chapter_contract_check` 增加：

```json
{
  "causal_transitions_grounded": true,
  "reader_inference_not_pre_resolved": true
}
```

### 7.2 Writer 默认提示词

保留视角、设定、燃料和场景结果约束，将泛化的“展示而非说教”补充为可执行规则：

```text
对每张 causal_transition：
1. visible_trigger 必须成为正文中可被当前视角观察到的事实。
2. trigger 出现后，让人物执行 character_next_action；不得让事件经过一段无关说明才继续。
3. 不得直接写出 reader_must_infer，也不得换一种措辞复述 narrator_must_not_state。
4. immediate_consequence 必须由人物选择实际造成，而不是由旁白宣布。
5. 保留 next_constraint，不要在同一段内把冲突解释并解决完。

技术参数只有在影响当下选择时才进入正文。参数出现后，应尽快转为指令、决定或操作，不继续科普。

允许视角人物作出带偏差的即时判断，但该判断必须影响行动，且不能等同于作者给出的正确答案。
```

不要增加“每段必须留白”“必须使用短句”“禁止所有心理描写”等规则。人工特征来自因果分配，不来自固定句型。

将目标字数由“偏差不得超过 15%”降为软性建议：

```text
以完整完成场景因果和章节契约为先。目标字数为参考，除非用户明确要求，不得为了贴近字数重复解释、增加无关感官细节或延长结尾总结。
```

### 7.3 Critic 默认提示词

新增要求：

- 对 Planner 每张转折卡完成 `causal_transition_check`。
- 不因句子短、段落不均或表达粗糙而判定有问题。
- 首先判断证据是否足够，再判断解释是否多余；不得盲目删除必要信息。
- 成功转折必须进入 `protected_strengths`。
- 新问题类型优先推荐专用操作：
  - `inference_overexplained` → `withhold_inference`
  - `action_preannounced` → `causalize`
  - `technical_exposition_unconverted` → `causalize`
  - `consequence_summarized` → `withhold_inference` 或 `tighten`
  - `causal_transition_missing` → `causalize`；若缺少必要剧情条件则 `scene_rewrite`

### 7.4 Reviser 默认提示词

增加两种操作边界，仍保持：只修改已选问题、保护段落不可动、不得新增剧情事实、默认保留至少 80% 原文。

特别约束：

- 不得把所有显式推理都删掉；只有证据足以支撑读者理解时才执行 `withhold_inference`。
- 不得把 `causalize` 理解为增加更多动作；必须让动作来自既有证据或约束。
- 删除方案总结后，要检查命令或选择是否仍有可理解依据。

### 7.5 Judge 默认提示词

Judge 同时比较原稿和修订稿的每张因果转折：

- 证据是否仍然存在；
- 人物下一步是否确实改变；
- 推论是否交给读者而非叙述者；
- 选择是否产生了正文可见后果；
- 新约束是否保留；
- 修订是否因删解释造成逻辑跳步；
- 修订是否变成故作玄虚、短句分镜或刻意不完整。

## 8. 严格结构化输出校验

实现者应为 Planner、Critic、Reviser、Judge 建立阶段级 Pydantic 输出模型或等价验证器，并在 `parse_json` 成功后执行语义校验。不能只检查“是 JSON 对象”。

最低要求：

- Planner：校验 `causal_transitions` 数量、ID 唯一性、枚举和必填字符串。
- Critic：校验问题类型、修订操作、转折卡覆盖完整、失败审计与 issue 的对应关系。
- Reviser：校验操作合法、issue 存在、保护段落未被 patch 命中、`revised_text` 非空。
- Judge：校验 decision 与 `final_text` 的条件关系，以及信息丢失时不能接受修订。

验证失败时保留原始响应并返回明确错误：

```text
PLANNER_OUTPUT_CONTRACT_INVALID
CRITIC_OUTPUT_CONTRACT_INVALID
REVISER_OUTPUT_CONTRACT_INVALID
JUDGE_OUTPUT_CONTRACT_INVALID
```

错误信息包含字段路径和原因，但不得包含 API Key 或 Provider 密钥。

## 9. 后端实现落点

实现者应优先沿用现有服务边界。

| 文件/目录 | 预期改动 |
| --- | --- |
| `apps/api/app/prompts/defaults.py` | 更新五阶段默认提示词和结构字段说明 |
| `apps/api/app/schemas/generation.py` | 增加两种修订操作；必要时添加检测反馈 API 请求模型 |
| `apps/api/app/llm/parser.py` 或新建 `app/llm/output_contracts.py` | 增加阶段级结构化输出模型和校验入口 |
| `apps/api/app/services/generation_service.py` | 在 JSON 解析后调用阶段合同校验；保持上下游候选传递不变 |
| `apps/api/app/llm/mock.py` | Mock Planner/Critic/Reviser/Judge 返回新字段和合法操作 |
| `apps/api/app/models/` | 新增检测反馈模型 |
| `apps/api/app/schemas/` | 新增检测反馈请求/响应模型 |
| `apps/api/app/repositories/` | 新增反馈数据访问层 |
| `apps/api/app/services/` | 新增反馈业务校验 |
| `apps/api/app/routers/` | 新增反馈 API 路由 |
| `apps/api/alembic/versions/` | 新增迁移；另加默认提示词兼容升级迁移 |
| `apps/web/src/features/generation/` | 展示因果转折、Critic 审计、Judge 对比和反馈录入 |
| `apps/web/src/types/` | 同步新合同类型 |

### 9.1 默认提示词升级兼容

现有项目允许用户修改和版本化提示词。升级必须延续当前“只升级未被用户修改的内建默认提示词”策略：

- 新安装直接创建新版默认提示词。
- 已安装数据库通过 Alembic 迁移更新仍保持旧默认内容、且未被用户编辑的内建版本。
- 用户自定义、复制或修改过的提示词绝不覆盖。
- 工作流若引用被安全升级的默认 Prompt Profile，应继续指向该 Profile 的最新版本。
- 迁移判断应使用旧版本完整内容或稳定哈希，不能只按名称判断。

## 10. 外部检测反馈

### 10.1 数据模型

新增表 `detector_feedbacks`，一条记录对应一个已存在的生成候选或最终采用版本。

建议字段：

```text
id                     string UUID, PK
project_id             FK projects, required
chapter_id             FK chapters, optional
run_id                 FK generation_runs, optional
candidate_id           FK generation_candidates, optional
chapter_version_id     FK chapter_versions, optional
detector_name          string, required
human_ratio            float, optional, 0..100
suspected_ai_ratio     float, optional, 0..100
ai_ratio               float, optional, 0..100
spans_json              text JSON, default []
notes                   text, default ""
created_at              datetime
updated_at              datetime
```

候选和章节版本至少提供一个。比例均存在时允许小数误差，总和应在 `99.5..100.5` 之间。

`spans_json`：

```json
[
  {
    "label": "human",
    "start_paragraph": 21,
    "end_paragraph": 25,
    "transition_ids": ["CT01"],
    "excerpt": "他正要合上盖板……许明远。"
  }
]
```

`excerpt` 只保存短摘录用于识别，不替代候选正文。段落编号必须以被检测的候选文本为准。

### 10.2 API

建议端点：

```text
POST   /api/detector-feedbacks
GET    /api/detector-feedbacks?project_id=&chapter_id=&candidate_id=
PATCH  /api/detector-feedbacks/{id}
DELETE /api/detector-feedbacks/{id}
```

创建时校验引用对象存在且属于同一项目。删除为物理删除即可，因为它是实验反馈，不是小说正文状态。

### 10.3 前端

在 Judge/最终采用区域增加可折叠的“外部检测反馈”：

- 选择检测对象：Writer、Reviser、Judge 合并稿或已采用章节版本；
- 输入检测器名称与三个比例；
- 逐项添加人工区间的起止段落；
- 可关联 Planner 转折卡；
- 展示同一章节不同候选的检测结果，但不显示“自动优化”按钮。

第一版不需要解析检测器截图，也不需要 OCR。用户手工录入即可。

## 11. 前端工作流行为

### Planner 面板

- 结构化展示每张因果转折卡。
- 显示类型、可见触发、下一行动、留给读者的推论、禁止明说内容、立即后果和新约束。
- 保留原始 JSON 查看与候选选择。

### Critic 面板

- 常规问题列表保持不变。
- 增加“因果转折审计”区域，逐卡显示 pass/fail/not_present。
- 新增两种修订操作到现有操作选择器。
- 成功转折对应的受保护段落要清晰标识。

### Reviser 面板

- 按既有方式展示 patch 和完整修订稿。
- 对 `withhold_inference` 和 `causalize` 显示中文名称与简短边界说明。

### Judge 面板

- 显示四个新总体验收字段。
- 逐卡展示原稿/修订稿状态和推荐版本。
- 当 `necessary_information_lost=true` 时明显警告，不允许界面暗示修订稿是默认选择；仍保留作者手动采用能力。

## 12. 错误处理和边界情况

1. Planner 输出 0 张转折卡：合法。Critic 和 Judge 对应数组为空，其他流程照常运行。
2. Planner 输出超过 3 张：候选合同无效，不能被选中进入 Writer。
3. 转折 ID 重复或格式错误：Planner 候选无效。
4. Writer 未呈现某张卡：Critic 标记 `not_present` 并创建 `causal_transition_missing`。
5. Writer 呈现了 trigger 但人物行动未改变：标记 `fail`，不得仅以“文字自然”为由通过。
6. Critic 保护段落与 issue 段落重叠：高严重度事实错误可要求 `scene_rewrite/manual_review`；普通问题不得突破保护。
7. Reviser 选择 `withhold_inference` 但证据不足：应保留原文或返回无法安全修订，不能硬删。
8. Judge 发现修订造成逻辑跳步：`necessary_information_lost=true`，对应 issue 为 `revision_worse`。
9. 外部检测比例缺项：允许保存部分比例；若三项都给出才验证总和。
10. 外部检测区间超出段落范围：API 拒绝，并返回具体 span 索引。
11. 历史运行没有新字段：查看仍正常；只在新执行时应用新合同。
12. 自定义旧提示词输出旧合同：允许用户继续查看和运行，但若工作流启用严格合同，应给出“提示词合同过旧”的明确错误和复制升级指引。不要静默篡改自定义提示词。

## 13. 自动化测试

### 13.1 后端单元与 API 测试

至少覆盖：

1. Planner 合法输出：空数组、1张、3张。
2. Planner 非法输出：4张、重复ID、非法 kind、空 trigger、空禁止列表。
3. Critic 必须覆盖全部 Planner 转折卡。
4. Critic fail/not_present 必须生成对应 issue。
5. 新 issue 类型和两种新操作能够通过选择 API。
6. 未选择的问题不能提交操作映射。
7. `withhold_inference`、`causalize` 正确进入 Reviser 渲染上下文。
8. Reviser patch 命中保护段落时合同验证失败。
9. Judge 信息丢失时不能 `accept_revision`。
10. Mock Provider 完整五阶段调用仍通过。
11. 默认提示词升级只影响未修改的内建版本。
12. 用户自定义提示词在迁移后逐字不变。
13. 检测反馈创建、查询、修改、删除和引用归属校验。
14. 三项检测比例总和的容差校验。
15. 历史运行缺少新字段时仍可读取。
16. API 错误不泄露密钥和完整 Provider 配置。

### 13.2 前端测试

至少覆盖：

1. Planner 卡片正确渲染 0—3 张转折。
2. Critic 审计状态与受保护段落显示正确。
3. 操作选择器包含中文显示的 `withhold_inference` 和 `causalize`。
4. 用户改选操作后请求体正确。
5. Judge 显示信息丢失警告和逐卡建议。
6. 检测反馈可创建、编辑和删除。
7. 候选切换后反馈对象与段落编号不会误关联旧候选。
8. 下游 stale 机制不受影响。

### 13.3 完整工程验证

实现完成后运行仓库已有检查：

```powershell
cd E:\3\novel-workbench\apps\api
.\venv\Scripts\python.exe -m pytest -v
.\venv\Scripts\alembic.exe upgrade head

cd E:\3\novel-workbench\apps\web
npm run lint
npx vitest run
npx vite build
```

如仓库已有 Playwright 环境，再运行现有 E2E。不能因 E2E 环境未启动而声称全部验收通过；应明确区分“自动化通过”和“环境未具备”。

## 14. 真实 LLM 验收（强制）

自动化和 Mock 通过不代表功能完成。必须使用项目管线真实调用本机已配置的 `opencode` Provider 与 `DeepSeek Pro` 模型验收。不得绕过项目服务直接请求模型。

### 14.1 对照原则

保持以下条件一致：

- 同一个小说项目及项目资料；
- 同一个章节契约和场景要求；
- 同一个 Provider、模型、temperature、top_p 和 token 上限；
- 同一组最近章节上下文；
- 只改变旧提示词管线与新因果转折管线。

模型若不支持 seed，应记录每次 attempt，并以多次调用降低偶然性。

### 14.2 三类测试场景

1. **线索发现**：接线盒编号、未来工单与人物父亲的潜在线索，验证 `evidence_to_action`。
2. **压力救援**：重力异常、缆绳承重、角色必须松手，验证 `constraint_to_choice`。
3. **普通对话**：没有悬疑或危险的工作/生活场景，验证 Planner 能输出空数组或自然的小型转折，不把所有章节改成悬疑动作模板。

每类场景至少进行：

- 旧管线 Writer 候选 3 次；
- 新管线完整五步 3 次；
- 新管线每次必须执行 Planner、Writer、Critic、选择问题、Reviser、Judge；
- 保存实际渲染提示词、模型 ID、参数、token、延迟、候选 ID 和最终选择。

### 14.3 管线级验收

每次新管线运行必须验证：

1. Planner 返回合法的 0—3 张转折卡。
2. Writer 正文实际包含 trigger、next_action、immediate_consequence 和 next_constraint。
3. Writer 没有直接复述 `reader_must_infer` 或禁区语义。
4. Critic 逐卡输出审计，并能发现故意插入的显式解释。
5. Reviser 只修改已选段落，不改变事实和场景结果。
6. Judge 能在修订更差时选择恢复原文或合并，而不是一律偏向修订稿。
7. 最终文本真实写入项目章节版本，并按现有机制镜像保存到 `E:\3\novel-workbench\data\chapters`。
8. API Key、密钥和敏感 Provider 配置不出现在日志、测试报告和提交中。

### 14.4 外部检测验收

将每个候选送入同一个外部检测器，手工记录比例和人工区间。验收重点不是单次总分，而是配对结果：

- 新管线在三类场景中至少两类的人工比例优于对应旧管线中位数；
- 至少两次人工区间与 Planner 的 `causal_transitions` 段落范围重叠；
- 不允许以小说逻辑破损、故意残句或随机噪声换取更高人工比例；
- 若检测结果没有改善，必须保存失败候选和反馈，报告“假设未被支持”，不能继续无限自动改稿，也不能声称通过。

外部检测器具有不稳定性。本验收只证明新结构在当前检测器和测试样本中的相对效果，不证明文本的真实作者身份，也不把检测结果用于处罚或事实判断。

### 14.5 验收报告

实现者应新增一份不含密钥的报告，例如：

```text
docs/validation/2026-07-xx-causal-transitions-real-llm.md
```

报告至少包含：

- 基线提交和实现提交；
- Provider 名称、模型展示名、参数；
- 项目、章节和 Run/Candidate ID；
- 每次 Planner 转折卡摘要；
- Critic/Judge 决策；
- 外部检测比例与人工区间；
- 旧/新管线对照表；
- 失败项、限制和最终结论。

不得把完整 API Key、加密密钥、请求鉴权头或敏感配置写进报告。

## 15. 实施顺序

推荐按以下顺序施工，每步完成后运行相关测试：

1. 添加阶段级结构化输出模型与合同验证测试。
2. 扩展 Planner 合同和 Mock Planner。
3. 更新 Writer 默认提示词与上下文快照测试。
4. 扩展 Critic 类型、审计合同和 Mock Critic。
5. 增加两种修订操作及 Reviser 合同。
6. 扩展 Judge 合同与原稿恢复规则。
7. 添加默认提示词安全升级迁移。
8. 更新前端类型和五阶段显示。
9. 实现检测反馈模型、API 和界面。
10. 跑后端、前端、迁移和 E2E 自动化。
11. 使用项目管线执行真实 DeepSeek Pro 对照验收。
12. 录入外部检测结果并提交验收报告。

不要先做界面再补合同。因果转折和修订边界属于后端数据合同，前端只负责呈现和编辑。

## 16. 完成定义

只有同时满足以下条件才能宣布完成：

- 五阶段默认提示词和数据合同已更新。
- Planner/Critic/Reviser/Judge 新字段经过严格后端验证，不只是提示词描述。
- 两种新操作可由 Critic 推荐、作者改选、Reviser执行、Judge验收。
- 自定义和历史提示词/运行不被破坏。
- 检测反馈能够关联候选、段落和转折卡。
- 后端 pytest、数据库迁移、前端 lint、Vitest 和 build 通过。
- 已通过项目自身五步服务真实调用 DeepSeek Pro，而非单独脚本直调。
- 已生成不含密钥的真实 LLM 与外部检测对照报告。
- 最终章节能够保存到数据库并镜像到 `data/chapters`。
- 没有提交本地数据库、API Key、密钥、生成小说正文备份或用户原有无关变更。

## 17. 实现者交接清单

开始前：

- 阅读本文全文。
- 阅读 `README.md`。
- 阅读现有局部修订设计与计划：
  - `docs/superpowers/specs/2026-07-17-revision-operations-design.md`
  - `docs/superpowers/plans/2026-07-17-revision-operations.md`
- 检查 `git status`，保留所有用户已有变更。
- 确认当前数据库迁移头和默认提示词升级迁移策略。
- 从项目现有 Provider 配置中识别 `opencode / DeepSeek Pro`；不得把密钥打印出来。

实施中：

- 使用测试驱动方式先写失败测试，再写实现。
- 每个任务限制在本文范围内，不做无关重构。
- 所有新枚举在后端、前端、Mock 和测试中保持一致。
- 结构化输出验证失败要产生可定位错误，不得静默降级。
- 不要用外部脚本绕过 `GenerationService` 冒充真实管线验收。
- 不要删除或覆盖已有候选、提示词版本和章节版本。

完成后：

- 给出变更文件列表和迁移版本。
- 给出自动化命令及实际结果。
- 给出真实 Run/Candidate ID 和外部检测对照报告路径。
- 明确报告未通过或受外部服务阻塞的检查。
- 检查 `git diff --check`、`git status` 和密钥泄漏。
- 只提交与本功能相关的代码、测试、迁移和验收文档。

## 18. 关键设计原则摘要

实现过程中如遇细节冲突，按以下优先级判断：

1. 小说因果和必要信息不能为检测器让路。
2. 让事实改变人物行动，比增加短句、专业数字或动作数量更重要。
3. 证据足够时才留白；证据不足时删除解释只会造成逻辑断裂。
4. 参数必须转成人物选择，选择必须产生后果，后果必须留下新约束。
5. 已成功的粗糙表达应受保护，不因“不够工整”被统一润色。
6. 检测结果用于对照学习，不用于自动无限改稿。
7. 所有真实验收必须经过项目管线，并留下可复核的运行证据。
