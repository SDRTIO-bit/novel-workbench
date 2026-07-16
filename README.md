# Novel Workbench

本地 AI 辅助小说写作工作台。支持五步写作流：场景规划 → 初稿 → 诊断 → 定点修订 → 对比验收。

## 技术栈

- 前端：React 19 + TypeScript + Vite 6 + Tailwind CSS 3 + TanStack Query 5 + Zustand 5
- 后端：FastAPI + SQLAlchemy 2 + Alembic + SQLite
- 测试：pytest + Vitest + Playwright
- API Key 仅保存在本机后端，不返回前端、不进入日志、不进入导出包

## 快速开始

### 环境要求

- Python >= 3.11
- Node.js >= 18

### 安装

```bash
# 后端
cd apps/api
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
# 初始化数据库
alembic upgrade head

# 前端
cd apps/web
npm install
```

### 启动开发环境

```bash
# Windows
.\scripts\dev.ps1

# macOS / Linux
./scripts/dev.sh
```

- 前端：http://localhost:8765
- 后端：http://localhost:8766
- API 文档：http://localhost:8766/docs

### 运行测试

```bash
.\scripts\test.ps1      # Windows：pytest + vitest
./scripts/test.sh        # macOS / Linux
```

单独运行：
```bash
cd apps/api && pytest -v         # 后端 161 个测试
cd apps/web && npx vitest run    # 前端单元测试
cd apps/web && npm run lint      # ESLint 检查
cd apps/web && npm run e2e       # Playwright E2E（需先启动前后端）
```

### 一键验收

```bash
npm run lint && npx vitest run && npx vite build
cd ../api && pytest -v && alembic upgrade head
```

## 项目结构

```
novel-workbench/
├── apps/
│   ├── api/                    # FastAPI 后端
│   │   ├── app/
│   │   │   ├── main.py         # 应用入口
│   │   │   ├── config.py       # 配置
│   │   │   ├── db.py           # 数据库引擎
│   │   │   ├── errors.py       # 统一错误格式
│   │   │   ├── models/         # SQLAlchemy 模型
│   │   │   ├── schemas/        # Pydantic 校验
│   │   │   ├── repositories/   # 数据访问层
│   │   │   ├── services/       # 业务逻辑
│   │   │   ├── llm/            # LLM 适配器
│   │   │   ├── prompts/        # 提示词模板
│   │   │   └── routers/        # API 路由
│   │   ├── alembic/            # 数据库迁移
│   │   └── tests/              # 后端测试 (161)
│   └── web/                    # React 前端
│       ├── src/
│       │   ├── api/            # HTTP 客户端
│       │   ├── app/            # 页面组件
│       │   ├── features/       # 功能模块
│       │   ├── stores/         # Zustand 状态
│       │   └── types/          # TypeScript 类型
│       ├── tests/              # Vitest 单元测试
│       └── e2e/                # Playwright E2E 测试
├── data/                       # 运行时数据
│   ├── novel_workbench.db      # SQLite 数据库
│   ├── .secret_key             # 加密密钥（自动生成）
│   └── exports/                # 导出文件
└── scripts/                    # 启动/测试脚本
```

## 核心功能

### 项目管理
- 新建、重命名、复制、软删除、恢复项目
- 8 类内建项目资料（梗概、大纲、人物、世界观、风格、原则、摘要、笔记）

### 章节编辑
- 新建、排序、重命名、软删除章节
- 800ms 防抖自动保存，带冲突检测（409）
- 手动创建版本与备注
- 恢复历史版本（自动备份当前内容）

### 导入导出
- 支持 TXT、Markdown、项目 JSON
- 自动识别章节标题（中文/英文）
- 编码回退（UTF-8 → UTF-8-SIG → GB18030）
- 导入先预览、确认后写入
- 导出包排除 API Key 和原始模型响应

### 提示词中心
- 5 类内置默认提示词（Planner/Writer/Critic/Reviser/Judge）
- 模板变量白名单 + 严格校验
- 版本化保存，不覆盖旧版本
- 复制、导出/导入自定义提示词
- 渲染预览（指定项目/章节/变量）

### 服务商与模型
- 支持 OpenAI-compatible 和 Mock provider
- Fernet 加密 API Key
- 连接测试、模型同步、手动添加模型
- 内置 Mock provider（无需真实 API 即可跑通全流程）

### 工作流方案
- 每步独立选择 Provider、Model、Prompt 版本
- 独立参数配置（temperature、top_p、max_tokens、timeout）
- 复制方案、设为默认

### 五步写作流
- Planner → Writer → Critic → Reviser → Judge
- 每步可单独执行、重试、切换模型/提示词
- 重试新增候选，不覆盖旧输出
- 每步执行前可预览上下文（来源、字符数、渲染后 prompt）
- 选择新上游候选自动标记下游 stale
- Critic 最多 5 个问题，选择修复项
- 最终采用时创建章节版本
- 上下文快照哈希确保预览与执行一致

## 备份方式

备份以下目录即可完整恢复：
```bash
# 备份
cp data/novel_workbench.db data/backup.db
cp data/.secret_key data/backup.secret_key

# 恢复
cp data/backup.db data/novel_workbench.db
cp data/backup.secret_key data/.secret_key
```

也可通过项目 JSON 导出功能逐个导出项目（不含密钥和原始响应）。

## 端口

| 服务 | 端口 |
|------|------|
| 前端开发服务器 | 8765 |
| 后端 API | 8766 |

## Mock Provider

内置 Mock provider 无需真实 API Key 即可跑通全部五步流程，返回各阶段的模拟 JSON 输出，适合开发测试和演示。
