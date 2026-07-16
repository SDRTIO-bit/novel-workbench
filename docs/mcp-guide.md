# Novel Workbench MCP 接入指南

## 快速概览

Novel Workbench 通过 MCP (Model Context Protocol) 暴露了 31 个工具，允许外部 AI（如 Claude Desktop、VS Code Copilot）全流程操控写作工作台：项目管理、章节编辑、5 步生成流水线。

## 获取令牌

启动后端服务时，访问令牌自动生成并存储在 `data/.mcp_token`（项目根目录下）：

```bash
cat data/.mcp_token
# 输出示例: 4B3s0uP027fytr9RB8Swu07DpI2rYn4ZIjxaUMPv6wQ
```

也可通过环境变量手动设置：

```bash
# .env 文件
NW_MCP_ACCESS_TOKEN=your-token-here
```

## 端点

- **MCP 端点**: `http://127.0.0.1:8766/mcp`（仅本地绑定）
- **传输方式**: Streamable HTTP (SSE)

## 鉴权

所有请求必须携带 `Authorization` 头：

```
Authorization: Bearer <token>
```

无令牌或错误令牌返回 `401 UNAUTHORIZED`。

## Claude Desktop 配置

编辑 Claude Desktop 的 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "novel-workbench": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```

## VS Code / Cline 配置

在 Cline 扩展的 MCP Servers 设置中添加：

```json
{
  "mcpServers": {
    "novel-workbench": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```

## 可用工具 (31 个)

### 项目管理 (8)
| 工具 | 说明 |
|------|------|
| `list_projects` | 列出所有项目 |
| `create_project` | 创建新项目 |
| `get_project` | 获取项目详情 |
| `update_project` | 更新项目属性 |
| `delete_project` | 软删除项目 |
| `restore_project` | 恢复已删除项目 |
| `get_project_documents` | 获取项目文档（大纲、世界观等） |
| `update_project_document` | 更新项目文档 |

### 章节管理 (7)
| 工具 | 说明 |
|------|------|
| `list_chapters` | 列出项目章节 |
| `create_chapter` | 创建新章节 |
| `get_chapter` | 获取章节完整内容 |
| `update_chapter` | 更新章节内容/标题 |
| `delete_chapter` | 软删除章节 |
| `restore_chapter` | 恢复已删除章节 |
| `reorder_chapters` | 重排章节顺序 |

### 版本管理 (3)
| 工具 | 说明 |
|------|------|
| `get_chapter_versions` | 获取章节版本列表 |
| `create_chapter_version` | 创建章节版本快照 |
| `restore_chapter_version` | 恢复到指定版本 |

### 生成流水线 (9)
| 工具 | 说明 |
|------|------|
| `create_run` | 创建生成运行 |
| `get_run` | 获取运行状态 |
| `list_runs` | 列出项目所有运行 |
| `execute_stage` | 执行流水线阶段 (planner/writer/critic/reviser/judge) |
| `select_candidate` | 选择候选结果 |
| `select_critic_issues` | 选择需修复的批评问题 |
| `cancel_run` | 取消运行 |
| `accept_final_text` | 接受生成文本写入章节 |
| `get_stage_status` | 获取阶段详情 |

### 上下文/配置 (4)
| 工具 | 说明 |
|------|------|
| `preview_context` | 预览 LLM 提示词上下文 |
| `list_workflows` | 列出工作流配置 |
| `list_providers` | 列出 LLM 提供商 |
| `list_prompt_profiles` | 列出提示词配置 |

## 典型使用流程

```
1. list_projects                → 找到目标项目
2. list_chapters                → 找到目标章节
3. get_chapter                  → 获取章节完整内容
4. list_workflows               → 选择工作流
5. create_run                   → 创建生成运行
6. execute_stage(planner)        → 执行第1步
7. execute_stage(writer)         → 执行第2步
8. execute_stage(critic)         → 执行第3步
9. execute_stage(reviser)        → 执行第4步
10. execute_stage(judge)         → 执行第5步
11. accept_final_text            → 接受生成结果写入章节
```
