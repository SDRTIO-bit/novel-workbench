# Novel Workbench

本地 AI 辅助小说写作工作台。支持五步写作流：场景规划 → 初稿 → 诊断 → 定点修订 → 对比验收。

## 技术栈

- 前端：React + TypeScript + Vite + Tailwind CSS
- 后端：FastAPI + SQLAlchemy + SQLite
- API Key 仅保存在本机后端

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

### 运行测试

```bash
# Windows
.\scripts\test.ps1

# macOS / Linux
./scripts/test.sh
```

## 数据目录

所有数据存储在 `data/` 目录下：
- `novel_workbench.db` — SQLite 数据库
- `.secret_key` — 加密密钥（自动生成）
- `exports/` — 导出文件
