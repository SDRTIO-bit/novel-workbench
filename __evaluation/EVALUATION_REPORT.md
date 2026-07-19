# GENERALIZATION_BATCH_V1 Evaluation Report

本报告记录冻结管线的执行证据；外部 GPT 的盲评、合同审计和阶段归因尚待通过 Evaluation MCP 写入 `results/`。

## Case execution

| Case | Pipeline status | Run |
| --- | --- | --- |
| CASE-001 | completed | 2acc9efb-b49b-4ffb-ac44-f0050875e5f2 |
| CASE-002 | failed | 0abf92f6-be51-46ff-b213-d9cbf45ae377 |
| CASE-003 | failed | 1c69a766-5af9-46e6-bba9-674dd24ec731 |
| CASE-004 | failed | 615bfb17-4ffa-48be-bbe5-5d186045d716 |

## External evaluation status

盲评胜负、Planner 合同 A/B 对比、Critic 命中/误报、Reviser 新增事实和 Judge 局部裁决均待独立 GPT 按 `GPT_EVALUATOR_PROMPT.md` 完成。CASE-002～004 在 Planner 基础设施失败后停止，因此没有文本可供盲评；它们不能被计入通过分母。

## Tokens, latency, and intervention

| Case | Input tokens | Output tokens | Total latency (ms) | Stage error |
| --- | ---: | ---: | ---: | --- |
| CASE-001 | 95982 | 55108 | 857703 | — |
| CASE-002 | 0 | 0 | 90 | LLM_ERROR |
| CASE-003 | 0 | 0 | 1 | LLM_ERROR |
| CASE-004 | 0 | 0 | 1 | LLM_ERROR |

人工介入次数为 0；运行器没有重试、没有变更 Prompt，也没有改写候选或最终稿。

## Passing criteria

- 盲评最终稿胜出：至少 3/4。
- 关键 Planner 合同错误少于 Writer：至少 3/4。
- 最终稿没有新增重要 Planner 之外剧情：4/4。
- stop state 准确：至少 3/4。
- Judge 局部裁决没有明显退化：至少 3/4。

## Supported conclusions and limits

`pipeline_evidence.json` 保存每个 Candidate 的原始响应、解析输出、选择关系、token、延迟、错误和最终来源映射。当前证据只支持“CASE-001 已导出可盲评基准；CASE-002～004 的第一次 Planner 调用失败且已停止”。在外部评估完成且至少三个新增案例取得可比较正文前，不能支持“冻结管线比单次 Writer 更稳定”的结论。单个案例失败不会触发 Prompt 修改建议。
