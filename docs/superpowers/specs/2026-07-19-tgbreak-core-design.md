# TGbreak Core 设计

## 事实边界

实现只依据本地源 `C:\Users\zhao\Downloads\TGbreak😺V3.0.5.json` 的审计结果。源文件原始 SHA-256 为 `f7aa69ee58503b9b38994fedb532d9cb3794b775fb9ad732ecdc7a69a7c2fa10`，文件末尾缺少数组和对象闭合符，导入器仅在内存中移除末尾逗号并补 `]}`，绝不修改源文件。`.local/` 只保存审计产物并由 Git 忽略。

## 架构

`app/tgbreak/importer.py` 负责从文件导入完整 prompt 元数据、原始数组顺序、原文内容、SHA-256 和 unsupported 字段。`app/tgbreak/renderer.py` 按数组顺序应用 Core Profile 的 identifier 覆盖，执行 `setvar/getvar`、注释块清理、外层变量替换和 Chat History / assistant 消息组装；它不改写源条目。

`app/tgbreak/profile.py` 根据审计确认的真实 identifier 创建 Core Profile，并只保存 `source_preset_id`、`source_sha256` 和 `entry_overrides`。`app/tgbreak/output.py` 对模型原文确定性提取闭合 `<draft_notes>`，保存 draft notes、正文和额外模块；缺失闭合标签直接失败。`app/tgbreak/models.py` 提供 dataclass 边界，数据库模型只保存用户私有导入内容和 profile 覆盖，不把源文件写入 migration。

## 数据流

项目适配层将 `project_documents`、`session_summary + recent_chapters`、`current_chapter_text / previous_writer_output`、`scene_instruction`、玩家角色名和叙事角色名映射到 `Story setting`、`interaction_record`、`ai_last_output`、`peip`、`user`、`char`。原生 Provider reasoning 固定为 `disabled`，请求元数据仍记录 `requested_reasoning_mode` 与 `reasoning_tokens`。

## 消息顺序

系统条目保持独立消息；marker `Chat History` 产生独立 chat-history 插槽；assistant 条目保持 assistant role，并位于用户消息后、模型续写前。不能将全部条目合并成一个 system 字符串。

## 错误与验证

未解析 `getvar` / `setvar` 宏、缺失闭合 `</draft_notes>`、源 SHA 不匹配和 source/profile 不一致均为显式失败。测试使用最小合成 fixture；真实文件只由非 CI dry-run 读取，命令不调用模型。
