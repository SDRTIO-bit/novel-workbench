# Planner v2 实验报告

## 1. MCP 执行情况

### 连接状态
- ✅ MCP 连接成功
- ✅ 枚举到 31 个工具
- ✅ 认证通过

### 实际调用的工具
1. `list_projects` - 列出项目
2. `create_project` - 创建项目"最后一课"
3. `update_project_document` - 设置项目文档（synopsis, outline, characters, world, style）
4. `create_chapter` - 创建章节"最后一课"
5. `create_run` - 创建 generation run
6. `execute_stage` (planner) - 执行 Planner
7. `select_candidate` (planner) - 选择 Planner 候选
8. `execute_stage` (writer) - 执行 Writer
9. `select_candidate` (writer) - 选择 Writer 候选
10. `execute_stage` (critic) - 执行 Critic
11. `select_candidate` (critic) - 选择 Critic 候选
12. `select_critic_issues` - 选择要修复的问题
13. `execute_stage` (reviser) - 执行 Reviser
14. `select_candidate` (reviser) - 选择 Reviser 候选
15. `execute_stage` (judge) - 执行 Judge
16. `select_candidate` (judge) - 选择 Judge 候选
17. `get_run` - 获取完整 run 状态
18. `get_stage_status` - 获取各阶段详细状态

### 各阶段执行情况

| 阶段 | 状态 | 重试次数 | 模型 | 备注 |
|------|------|----------|------|------|
| Planner | ✅ 成功 | 3次失败后使用 Mock | deepseek-v4-pro → mock-model | opencode API 频率限制，DeepSeek 余额不足 |
| Writer | ✅ 成功 | 0 | mock-model | 一次通过 |
| Critic | ✅ 成功 | 0 | mock-model | 一次通过 |
| Reviser | ✅ 成功 | 0 | mock-model | 一次通过 |
| Judge | ✅ 成功 | 0 | mock-model | 一次通过 |

### 模型和 Prompt 版本
- Provider: 本地演示 (Mock)
- Model: mock-model
- Planner Prompt: 内置默认（Planner v2 合同）
- Writer Prompt: 内置默认
- Critic Prompt: 内置默认
- Reviser Prompt: 内置默认
- Judge Prompt: 内置默认

## 2. Planner v2 结果

### 完整 Planner JSON
保存路径：`E:\3\novel-workbench\.tmp\03-planner-parsed.json`

### 因果卡逐项评价

**CT01 - evidence_to_action**

| 字段 | 内容 | 评价 |
|------|------|------|
| visible_trigger | 书店铜铃响起，门口出现一个红着眼眶的小女孩 | ✅ 是人物当时实际能感知的事实 |
| character_interpretation | 老陈看出女孩需要安全感 | ⚠️ 部分问题：这是作者全知视角的推断，不是从具体证据产生的判断。缺少"女孩攥紧书包带子"等具体观察证据 |
| character_next_action | 老陈用最平常的语气请她进来坐 | ✅ 是基于判断的合理行动 |
| rejected_alternative | 直接询问女孩为什么哭 | ✅ 是真实可行的另一条行动 |
| reader_must_infer | 老陈选择用日常感而非直接询问来安抚 | ✅ 合理，读者可以推断 |
| narrator_must_not_state | ["老陈判断女孩需要安全感", "这是最好的处理方式"] | ✅ 正确设置了叙述者禁区 |
| immediate_consequence | 女孩跨过门槛，阿橘走到她脚边坐下 | ✅ 在正文中可见 |
| counterfactual_without_action | 如果老陈不邀请，女孩会继续站在门外 | ✅ 合理反事实 |
| state_delta.before | 女孩站在门外犹豫 | ✅ 清晰 |
| state_delta.after | 女孩进入书店坐下 | ✅ 清晰，改变了后续行动空间 |
| cost_or_commitment | 老陈打破了自己不干涉他人事务的习惯 | ✅ 有代价/承诺 |
| next_constraint | 老陈还不知道女孩为什么哭以及她从哪里来 | ✅ 是行动新造成的限制 |

### 10 项核验问题回答

1. **visible_trigger 是否是人物当时实际能感知的事实？**
   ✅ 是。铜铃声和红眼眶的女孩都是可感知的。

2. **character_interpretation 是否由该证据产生，而不是作者全知答案？**
   ⚠️ 部分问题。"看出女孩需要安全感"缺少具体观察证据支撑，更像是作者直接给出的判断。

3. **rejected_alternative 是否是真实可行的另一条行动？**
   ✅ 是。直接询问是合理的替代方案。

4. **人物的选择是否关闭了一条退路，或带来了责任、代价、暴露？**
   ✅ 是。"打破不干涉他人事务的习惯"是代价。

5. **如果人物不采取该行动，immediate_consequence 是否确实不会以相同方式发生？**
   ✅ 是。反事实合理。

6. **state_delta.before 和 after 是否真的改变了人物后续行动空间？**
   ✅ 是。从"门外犹豫"到"进入书店坐下"，行动空间明显改变。

7. **next_constraint 是否是人物行动新造成的，而非开场前已有问题？**
   ✅ 是。"不知道女孩为什么哭"是因为邀请她进来后才需要面对的问题。

8. **转折是否由人物选择推动，而非猫、巧合、电话、天气或陌生人突然替人物解决？**
   ✅ 是。老陈主动邀请是人物选择。

9. **stop_state.visible_fact 是否能够直接证明局面已改变？**
   ✅ 是。"女孩坐在书店里"直接证明关系已建立。

10. **Planner 是否仍存在"字段全部填写，但实际因果为空"的情况？**
    ⚠️ 存在轻微问题。character_interpretation 字段虽然填写了，但缺少具体证据链，有"假因果"倾向。

### 总体评价
Planner v2 合同结构完整，所有必填字段都已填写。但 `character_interpretation` 字段存在"作者全知"倾向，缺少从具体观察到推断的因果链。这是 Mock 输出的问题，真实模型可能表现不同。

## 3. Writer 初稿结果

### 完整初稿
保存路径：`E:\3\novel-workbench\.tmp\04-writer-draft.txt`

### Planner 字段落地情况

| Planner 字段 | 是否落地 | 说明 |
|--------------|----------|------|
| entry_pressure | ✅ | "门上的铜铃突然响了" |
| visible_trigger | ✅ | "门口的光线里站着一个小小的身影——一个背书包的女孩，头发有点乱，眼眶红红的" |
| character_next_action | ✅ | "用最平常的语气说了三个字——'进来坐。'" |
| immediate_consequence | ✅ | "女孩犹豫了一下，跨过了门槛" |
| reader_must_infer | ✅ | 没有直接说明老陈的判断过程 |
| narrator_must_not_state | ✅ | 没有说出"老陈判断女孩需要安全感" |
| next_constraint | ✅ | 结尾保留了悬念 |
| stop_state.visible_fact | ✅ | "阿橘从窗台上跳下来，悄无声息地走到女孩脚边，坐了下来" |

### 10 项核验问题回答

1. **是否从 entry_pressure 对应的具体行动开始？**
   ⚠️ 不是。开篇是环境描写，铜铃响在第四段。

2. **是否真正写出了 visible_trigger？**
   ✅ 是。详细描写了女孩的外貌和姿态。

3. **人物是否根据自己的判断执行了 character_next_action？**
   ✅ 是。老陈用平常语气邀请。

4. **immediate_consequence 是否在正文中可见？**
   ✅ 是。女孩跨过门槛。

5. **是否泄漏了 reader_must_infer？**
   ✅ 没有泄漏。

6. **是否直接或换句话说出了 narrator_must_not_state？**
   ✅ 没有说出。

7. **是否保留了 next_constraint？**
   ✅ 是。结尾没有解释女孩为什么哭。

8. **是否在 stop_state.visible_fact 成立后立即停止？**
   ✅ 是。女孩坐下后结束。

9. **是否又回到"环境描写—温柔动作—情绪软化"的顺滑治愈模板？**
   ⚠️ 有倾向。整体氛围偏治愈，但不算严重。

10. **是否出现角色始终判断正确、没有代价、方便角色自动解决问题？**
   ✅ 没有。老陈的行动有代价（打破习惯）。

### 总体评价
Writer 初稿质量较高，Planner 中的关键约束都得到了执行。但开篇节奏偏慢，环境描写过长。

## 4. 修订结果

### Critic 选择的问题
- I02 (medium): '进来坐'三字过于简练，可加一两个小动作丰富层次
- I05 (medium): 猫阿橘的情感线索在结尾处收束不足，缺少呼应

### Reviser 改了什么
Mock 输出为占位文本，实际修订内容不可见。

### 最终稿与初稿的主要差异
Mock 输出无法展示真实差异。

## 5. 实验结论

**选择：E. MCP 或运行环境问题导致实验无效**

### 证据
1. **opencode provider (deepseek-v4-pro)**: 连续 2 次返回 `LLM_RATE_LIMIT` 错误
2. **DeepSeek provider (deepseek-chat)**: 返回 `Insufficient Balance` 错误
3. 最终使用 **Mock Provider** 完成流程，Mock 输出是固定模板，无法验证 Planner v2 在真实模型调用中的实际效果

### 说明
本次实验成功验证了：
- ✅ MCP 连接和工具调用正常
- ✅ Planner v2 合同结构完整
- ✅ 5 步流程可以跑通
- ✅ 各阶段数据流转正常

但无法验证：
- ❌ Planner v2 在真实模型调用中的实际效果
- ❌ Writer 是否真正执行了 Planner 的约束
- ❌ Critic/Reviser/Judge 的真实输出质量

## 6. 下一步建议

**最优先动作：解决 API 可用性问题**

1. 为 opencode provider 增加请求间隔或重试机制
2. 为 DeepSeek provider 充值或更换 API Key
3. 配置 Kimi K3 或其他可用模型

只有在真实模型可用的情况下，才能进行有效的 Planner v2 行为实验。

---

**实验时间**: 2026-07-18
**实验者**: Sisyphus
**项目**: 最后一课 (4c8d77e3-ec87-44dd-bffa-161eefc5cacf)
**Run ID**: 76a99772-c4ff-4096-a374-09fc55661da2
