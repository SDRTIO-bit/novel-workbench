# 编码损坏说明（ENCODING NOTE）

`CASE-001.json` 中 `blind_pass.evidence` 字符串为 `???` 乱码：外部评估方导出该
文件时使用了非 UTF-8 编码，中文证据句已不可恢复。

- 盲评决定本身在打开 source mapping 之前完成并记录，决定不受影响；
- 受损的仅是证据引文字符串，不影响 contract_pass / pipeline_pass 结构化字段；
- 若需引用本案例证据，请重新导出或重新运行评估。

记录：2026-07-19，Phase 0 合并审查修复。
