# KnowGraph — 仓库指南 (for OpenCode)

## 概览

Monorepo：Python 后端 (`backend/`) + React 前端 (`frontend/`)。从海外博物馆爬取中国文物数据，构建知识图谱 (Apache AGE + PostgreSQL)，提供 RAG 智能检索与 AI Agent 对话。

## 常用命令

以下命令在项目根目录执行。

```bash
# 启动数据库 (Podman)
just database

# 初始化/重建/清理 数据库
just initdb

# 启动后端 (端口 40001)
just web

# 启动前端 (端口 5173)
just ui

# 后端 lint / typecheck / 格式化
just backend-lint
just backend-typecheck
just backend-format

# 前端 lint / typecheck
just frontend-check
just frontend-typecheck

# 运行后端测试 (必须在 backend/ 下执行)
cd backend && uv run pytest
```

## 架构

### 后端 (`backend/`)

- 入口：`knowgraph/__main__.py` → CLI 命令 `uv run knowgraph <command>`
- 应用：`knowgraph/routers/__init__.py` → FastAPI，路由 `/api/chat`、`/api/rag`、`/api/graph`、`/api/users`，MCP 协议端点为 `/mcp`
- 认证：`/api/login`、`/api/register`、`/api/refresh`、`/api/me` (JWT)
- Agent：`knowgraph/chat/model.py` — pydantic-ai Agent，3 个 toolsets (rag/code/web)
- 数据库：PostgreSQL + vchord (向量) + vchord_bm25 (全文检索) + Apache AGE (图数据库)
- 详细模块文档见 `backend/AGENTS.md`

### 前端 (`frontend/`)

- React 19 + Ant Design 6 + Vite 8 + TypeScript
- Lint/格式化：Biome (`pnpm check`)
- Type check：tsgo (`pnpm type-check`)

### 两类适配器模块 — 切勿混淆

- `knowgraph/adapters/` — CSV 导入适配器 (PhilaMuseumAdapter, MetMuseumAdapter, AsianArtAdapter)，配合 `ingest csv` 使用
- `knowgraph/spider/adapters/` — 网页爬虫适配器 (PhilaMuseumCrawlerAdapter, MetMuseumCrawlerAdapter, AsianArtCrawlerAdapter)，配合 `spider` 使用

### 迁移脚本

- `python -m knowgraph.migration.migrate_to_mysql` — AGE 图 → MySQL
- `python -m knowgraph.migration.migrate_to_neo4j` — 三元组 → Neo4j
- 均支持 `--dry-run`、`--limit N`、`--clean`

## 关键约定

- **Python 3.14**：不需要 `from __future__ import annotations`，不需要为类型加字符串引号
- **包管理**：uv (Python)，pnpm (Node.js)
- **Lint**：ruff (后端)，Biome (前端)。遇到 lint/typecheck 错误请随手修复
- **格式化**：ruff format — 每行 120 字符，双引号，LF 换行
- **Type check**：ty (后端)，tsgo (前端)
- **User agent**：全局设为 Chrome 139 (`environments.py`)，爬虫使用 curl_cffi Chrome 146 指纹反反爬
- **端口**：后端 40001，PG 容器内 5432 映射到宿主机 10004（见 `.env` 或 `EnvironmentSettings`）
- **测试依赖运行中的 PostgreSQL**（需要 vchord、BM25、AGE 扩展），大多数测试是集成测试，会创建 `test_data` 数据库
- **容器**：使用 `podman-compose`，不是 `docker-compose`
- **环境变量**：项目根目录 `.env` 自动加载，优先级：环境变量 > `.env` > 类默认值
