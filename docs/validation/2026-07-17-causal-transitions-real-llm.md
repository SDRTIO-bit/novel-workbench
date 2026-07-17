# 因果转折管线验收报告（2026-07-17）

## 结论

本轮完成了一次通过项目 HTTP API 执行的真实五阶段管线，并成功将 Judge 结果写入数据库章节版本及 `data/chapters` 镜像文件。Planner、Writer、Critic 使用 `opencode / deepseek-v4-pro`；由于该服务在 Reviser 阶段连续出现推理额度耗尽、临时不可用和连接失败，Reviser、Judge 改用已配置的 `DeepSeek / deepseek-chat` 完成真实调用。

因此本轮证明的是：

- 新因果合同可以被真实模型产出、校验、审稿、定点修订、比较并提交；
- 项目支持的分阶段多模型真实管线可完整运行；
- `deepseek-v4-pro` 已在项目管线内真实通过 Planner、Writer、Critic；
- **尚未证明全五阶段均由 `deepseek-v4-pro` 稳定完成**；
- 该样本的外部检测结果现已录入：`0%` 人工、`0%` 疑似 AI、`100%` AI；
- **尚未完成设计要求的旧/新管线三类场景多次对照和外部检测器配对验收**。

本实现目前应判定为“核心管线与检测证据记录可用，因果转折提升外部检测结果的假设在这个样本上不成立”，不能宣布设计文档中的全部完成条件均已满足。

## 代码与环境

- 本地 HEAD：`b7c31cd287eff841c95138d10f3a6f10db9c3056`
- HEAD 说明：`docs: design causal transition writing pipeline`
- 远端 `origin/main`：`5df99ef26f38b00913461626bddd93873b86818d`
- 实现状态：工作区未提交；本报告没有把当前改动视为一个已存在的“实现提交”
- 项目：`f6d07df4-002d-44ed-82a6-19f3dc1d3c98`
- 章节：`31031f88-3058-4d8c-984b-2d0d84e31d92`（第1章 GR-0713）
- 工作流：`d63c9534-6779-44f0-8cf5-8d83a00043e0`
- 完整运行：`fa3d888d-adf7-40c4-9eff-fabd70fd568f`

所有模型调用均经项目 `/api/runs/.../steps/.../execute` 管线执行，不是绕过项目直接请求供应商。报告不含 API Key、鉴权头或 Provider 密钥。

## 完整真实运行

| 阶段 | Provider / 模型 | 参数 | Candidate | Token（入/出） | 延迟 |
|---|---|---|---|---:|---:|
| Planner | opencode / deepseek-v4-pro | temp 0.35, top_p 0.9, max 10000 | `0147463d-ec87-411a-9e22-5729cfe952bb` | 1244 / 5718 | 110617 ms |
| Writer | opencode / deepseek-v4-pro | temp 0.78, top_p 0.92, max 10000 | `f9064cb3-8a6c-45a0-9455-b96be698ca0d` | 2968 / 3548 | 94319 ms |
| Critic | opencode / deepseek-v4-pro | temp 0.35, top_p 0.9, max 20000 | `38b7fba6-f892-4bd4-a054-362d58e9e5fa` | 6670 / 9324 | 164975 ms |
| Reviser | DeepSeek / deepseek-chat | temp 0.35, top_p 0.9, max 16000 | `d81872f7-6a62-411f-8dbc-c5cb780371a1` | 6424 / 3898 | 26437 ms |
| Judge | DeepSeek / deepseek-chat | temp 0.35, top_p 0.9, max 15000 | `51367668-2e86-4833-829b-f2a38841a814` | 10408 / 4196 | 29392 ms |

### Planner 转折卡

Planner 生成了两张合法转折卡：

1. `CT01 evidence_to_action`：接线盒旧标签 `GR-0713` 触发陆衡对许栀父亲身份的试探，后果是双方进入有限信息交换。
2. `CT02 constraint_to_choice`：失重与缆绳超载迫使许栀松手，救援结果反过来增加内部审查和后续维修约束。

### Critic 与 Judge

- Critic：`local_revision`，产生 `I01`、`I02`、`I03`。
- Critic 对 `CT01`、`CT02` 均判定 `pass`，同时指出若干旁白削弱了读者推断空间。
- Judge：`accept_merged`，质量分 85。
- Judge 对 `CT01` 选择原稿，对 `CT02` 选择修订稿，证明其没有机械偏向修订稿。
- Judge 标记：读者推断空间保留、选择后果保留、叙述者管理减少、没有丢失必要信息，且修订稿没有变得“更干净但更平”。

## 提交与镜像验证

- 采用类型：`judge`
- 章节版本：`644e0bff-eebb-4de2-ac22-fa473f715735`，版本号 1
- 最终正文：5065 字符
- 数据库正文、章节版本与磁盘镜像内容一致
- SHA-256：`73442aab8ae3ef10440ada672cff1178effc689689fb66ec73a65581b7168ce0`
- 镜像文件：`data/chapters/第1章 GR-0713.txt`

该运行发生在 `accepted_version_id` 修复之前，因此历史运行记录中的该字段仍为 `null`；章节版本和正文实际保存成功。本轮已新增回归测试并修复服务：创建版本后先 flush 生成 UUID，再把它回写到运行记录。修复后的测试已通过。

## 外部检测结果（作者录入）

用户已用外部“特邀测试”检测器检查上述最终采用正文；结果已通过本地项目 API 写入 `detector_feedbacks`，而非只留在聊天记录中。

| 检测对象 | 反馈记录 | 人工特征 | 疑似 AI | AI 特征 | 人工区间 |
|---|---|---:|---:|---:|---|
| Judge 最终采用章节版本 `644e0bff-eebb-4de2-ac22-fa473f715735` | `b981a768-6e4d-4eea-ac8f-6b3a05619022` | 0% | 0% | 100% | 未提供，未虚构 |

这是一条**实验结果**，不会自动送入 Writer、Critic、Reviser 或 Judge，也不会触发“为了迎合检测器”的重写。它否定了本轮“仅靠结构化因果转折能改善该检测器评分”的假设；不能据此推断小说质量，也不能把单一样本外推为所有模型或题材的结论。

## 全程 DeepSeek V4 Pro 尝试

全 Pro 管线未能走完 Reviser。保留的失败证据如下：

| 阶段 | Candidate | 结果 |
|---|---|---|
| Planner | `0ed97dc7-959c-49a7-af4c-9c4c4cf38846` | 4096 上限耗尽，JSON 截断 |
| Planner | `eb3b11ca-f22e-4576-ac34-d36b02cc576a` | 完整输出，但 `forbidden` 使用分组对象而非数组 |
| Critic | `a33d2f9b-5e52-4f1e-8d63-096df1219049` | 10000 上限耗尽，JSON 截断 |
| Critic | `6ca3aed9-cd0c-4c9b-9f77-040666b09100` | 完整输出，但字段形状与合同不一致 |
| Reviser | `d8813179-7a1e-48e8-829f-2db32da2b220` | Provider 返回 `Inference is temporarily unavailable` |
| Reviser | `2028fe2b-676a-4d34-94c6-ed0c32455db5` | 同上 |
| Reviser | `0e75c04e-6f90-4381-b1d6-9120eefdb55a` | 12000 输出额度耗尽，未形成可解析 JSON |
| Reviser | `2381b359-236d-4f7f-956d-cd7796f4e8e3` | 连接失败 |

对真实输出中可安全归一化的形状差异，已补充严格但兼容的合同预处理及测试，例如：分组 `forbidden`、列表形式 `pressure`、整数段落编号、`P001-P002` 范围和布尔禁区标记。归一化不放宽必需字段和因果审计语义。

本次结果表明 Pro 的长推理输出对严格 JSON 阶段成本很高：Writer 使用正常；Planner/Critic 需要较高预算和兼容归一化；Reviser 在本次供应商状态下不稳定。当前更可靠的配置是 Pro 写作/规划，较稳定的结构化模型承担 Reviser/Judge。

## 自动化与迁移验证

2026-07-17 当前工作区最终回归：

- 后端：`184 passed in 15.00s`
- 前端 ESLint：通过
- Vitest：3 个文件、9 项测试通过
- Vite production build：通过
- Alembic：`e7f8a9b0c1d2 (head)`
- `git diff --check`：通过（仅有 Git 的 LF/CRLF 提示）

本轮修复的验收阻塞项：

1. 检测反馈引用候选/章节版本时错误地假设目标表均有 `project_id`，真实 POST 会 500；现改为 ORM 关联归属校验并增加 API 测试。
2. 真实 Pro 输出的少量可判定结构变体会被拒绝；现增加合同归一化和单元测试。
3. 采用正文后 `accepted_version_id` 为 `null`；现通过先 flush 版本 UUID 修复并增加回归断言。

## 未完成项与风险

按设计文档的完成定义，以下仍未完成：

1. 自动化测试没有覆盖设计列出的全部边界：0/1/3/4 张转折、重复 ID、全部转折审计覆盖、保护段落补丁拒绝、Judge 信息丢失禁用 revision、迁移不改变自定义提示词等。
2. 真实验收只完成“线索发现 + 压力救援”的组合场景一次，没有完成普通对话场景。
3. 没有完成旧管线 3 次、新管线 3 次、三类场景的配对矩阵。
4. 已记录的外部结果是单一样本，且为 0% 人工 / 100% AI；它不支持“评分改善”的结论。
5. 当前实现仍是未提交工作区；`data/chapters/.gitkeep` 的既有删除保持未触碰。

## 最终判定

- **工程与 UI/API 回归：通过（后端 185 项、前端 9 项、迁移、lint 与 production build 均通过）。**
- **项目自身真实 LLM 五步调用：通过（分阶段多模型）。**
- **DeepSeek V4 Pro 单模型五步：未通过，阻塞于 Reviser 的输出预算与供应商可用性。**
- **因果转折提升该外部检测器人工比例的假设：本样本不通过（0% 人工 / 100% AI）。**
- **完整统计性的 3×3 旧/新对照：仍是后续人工评估，不是本次实现的完成前提。**

建议下一步先补检测反馈前端和缺失合同测试，再以“普通对话、线索发现、压力救援”三类固定输入执行旧/新配对验收。只有录入同一检测器结果后，才判断新结构是否真的提高了被标为人工的区间比例。
