# KnowGraph — 海外中国文物知识图谱系统

**Overseas Chinese Cultural Artifact Knowledge Graph System**

基于 RAG (检索增强生成) 的知识图谱系统，专注于从海外博物馆网站爬取中国文物信息，构建结构化知识图谱，支持智能问答、混合检索与可视化展示。

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.14, FastAPI, pydantic-ai, SQLModel, FastMCP |
| **前端** | TypeScript, React 19, Ant Design 6, Vite 8 |
| **数据库** | PostgreSQL 18 + vchord (向量) + vchord\_bm25 (全文检索) + Apache AGE (图数据库) |
| **AI** | DeepSeek / OpenAI (pydantic-ai Agent), BGE-M3 (嵌入/重排序), SiliconFlow API |
| **爬虫** | Scrapy, curl-cffi (Chrome 146 指纹, 突破 Cloudflare) |
| **容器化** | Docker / Podman, docker-compose |
| **包管理** | uv (Python), pnpm (Node.js) |

## 功能特性

- **数据爬取** — 从 8+ 海外博物馆 (大都会博物馆、史密森尼、克利夫兰艺术博物馆等) 采集中国文物数据，自动处理反爬机制
- **AI 清洗** — 基于大模型实现字段标准化、去重、图片有效性验证
- **知识图谱** — 参考 CIDOC-CRM 国际标准，将文物数据转化为实体-关系三元组
- **混合检索** — 向量相似度 + BM25 全文检索 + 图遍历的 RAG 管道
- **AI Agent** — 支持工具选择 (RAG 检索 / Python 代码执行 / 网页搜索)，SSE 流式响应
- **MCP 协议** — 通过 `/mcp` 端点暴露工具，支持外部 LLM 集成
- **用户认证** — JWT 认证体系
- **管理后台** — React 前端仪表盘，支持文物检索、知识图谱可视化

## 快速开始

### 前置要求

- Python 3.14+
- Node.js 22+
- pnpm
- uv
- Docker / Podman (用于数据库)

### 1. 启动数据库

```bash
just database
```

或手动:

```bash
cd docker && docker-compose up database -d
```

### 2. 初始化数据库

```bash
just initdb
```

### 3. 启动后端

```bash
just web
```

后端运行在 `http://127.0.0.1:40001`

### 4. 启动前端

```bash
just ui
```

前端运行在 `http://localhost:5173`

## 项目结构

```
graph/
├── backend/                 # Python 后端
│   └── knowgraph/
│       ├── __main__.py      # CLI: knowgraph {start|database|spider}
│       ├── routers/         # FastAPI 路由 (chat, rag, user)
│       ├── chat/            # AI Agent (pydantic-ai)
│       ├── database/        # 数据库层 (SQLModel, AGE, vchord)
│       ├── documents/       # 文档处理 (转换/分块/嵌入)
│       ├── graph/           # 知识图谱本体 (CIDOC-CRM)
│       ├── spider/          # 博物馆爬虫 (Scrapy)
│       ├── tools/           # FastMCP 工具
│       └── utils/           # 配置与工具
├── frontend/                # React + TypeScript 前端
│   └── src/
│       ├── App.tsx          # 主仪表盘
│       └── main.tsx         # 入口
├── docker/                  # 容器化部署
│   ├── docker-compose.yaml
│   ├── database/Dockerfile  # PG18 + vchord + AGE
│   └── web/Dockerfile       # FastAPI 多阶段构建
├── justfile                 # 命令快捷方式
├── TODO.md                  # 开发计划
└── pyproject.toml           # 根级工具配置
```

## 命令参考

### CLI

所有命令通过 `uv run knowgraph` 调用。

| 命令 | 选项 | 说明 |
|------|------|------|
| `start` | — | 启动 FastAPI 服务器 |
| `database <mode>` | `--dbname, -d` | 数据库管理：`init` 初始化, `reset` 重建, `clean` 清理 |
| `spider <museum...>` | — | 运行爬虫采集指定博物馆数据 |
| `search <query>` | `--top, -k` 结果数 (默认 5)<br>`--graph/--no-graph` 图谱搜索 (默认 on)<br>`--max-hops, -h` 最大跳数 (默认 2)<br>`--vector-weight` 向量权重 (默认 0.4)<br>`--bm25-weight` BM25 权重 (默认 0.3)<br>`--graph-weight` 图谱权重 (默认 0.3) | 混合检索 (向量+BM25+图谱) |
| `ingest csv` | `--data-dir, -d` CSV 目录<br>`--adapter, -a` 适配器 (philamuseum / philamuseum_raw)<br>`--ingest/--no-ingest` 是否同时提取文档<br>`--llm/--no-llm` LLM 三元组提取<br>`--dedup` 去重阈值 (默认 0.95) | 从 CSV 导入文物原始数据 |
| `ingest artifacts` | `--museum, -m` 按博物馆筛选<br>`--limit, -n` 最大数量<br>`--llm/--no-llm` LLM 三元组提取<br>`--skip-ingested/--no-skip-ingested` 跳过已摄入<br>`--dedup` 去重阈值 (默认 0.95) | 从文物表提取文档到 DocumentTable |
| `check-similar <content>` | `--threshold, -t` 相似度阈值 (默认 0.95)<br>`--top, -n` 最大结果数 (默认 5) | 检查文档相似度 |

### just 快捷命令

| 命令 | 说明 |
|------|------|
| `just web` | 启动后端服务器 |
| `just ui` | 启动前端开发服务器 |
| `just initdb` | 初始化数据库 |
| `just database` | 启动数据库容器 |
| `just docker` | 启动所有容器 |
| `just build-ui` | 构建前端并同步到 static/ |

### 开发命令

| 命令 | 说明 |
|------|------|
| `cd backend && pytest` | 运行后端测试 |
| `cd backend && ruff check knowgraph/` | 代码检查 |
| `cd backend && ty check knowgraph/` | 类型检查 |

## 已支持的博物馆

- Cleveland Museum of Art (克利夫兰艺术博物馆)
- Metropolitan Museum of Art (大都会艺术博物馆)
- Smithsonian Institution (史密森尼学会)
- Freer+Sackler Galleries (弗利尔+赛克勒美术馆)
- Princeton University Art Museum (普林斯顿大学艺术博物馆)
- Nelson-Atkins Museum of Art (纳尔逊-阿特金斯艺术博物馆)
- Art Institute of Chicago (芝加哥艺术博物馆)
- Philadelphia Museum of Art (费城艺术博物馆)
- American Museum of Natural History (美国自然历史博物馆)

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FASTAPI_HOST` | `127.0.0.1` | 后端监听地址 |
| `FASTAPI_PORT` | `40001` | 后端端口 |
| `POSTGRES_HOST` | `127.0.0.1` | 数据库地址 |
| `POSTGRES_PORT` | `40002` | 数据库端口 |
| `POSTGRES_USER` | `postgres` | 数据库用户 |
| `POSTGRES_PASSWORD` | `postgres` | 数据库密码 |
| `JWT_SECRET` | `knowgraph-jwt-secret-...` | JWT 密钥 |
| `RELEASE_MODE` | `True` | 发布模式开关 |

## 许可证

本项目未明确许可证。
