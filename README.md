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
| **爬虫** | Scrapy, curl-cffi (Chrome 146 指纹), httpx, Playwright, asyncio 并发 |
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
│       ├── spider/          # 博物馆爬虫
│       │   ├── __init__.py
│       │   ├── spider.py     # ArtifactSitemapSpider (网站地图模式)
│       │   ├── crawler.py    # AdapterCrawler (异步适配器模式, 40 并发)
│       │   ├── adapters/     # 博物馆爬虫适配器 (按网站定制)
│       │   ├── config.py     # MuseumConfig 博物馆配置
│       │   ├── runner.py     # ScrapyCrawler 爬虫运行器
│       │   └── ...
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

所有命令通过 `uv run knowgraph` 调用（迁移命令除外）。

| 命令 | 选项 | 说明 |
|------|------|------|
| `start` | — | 启动 FastAPI 服务器 |
| `database <mode>` | `--dbname, -d` | 数据库管理：`init` 初始化, `reset` 重建, `clean` 清理 |
| `spider <museum...>` | — | 运行爬虫采集指定博物馆数据。支持网站地图模式 (`cleveland`, `metropolitan`, ...) 和适配器模式 (`metropolitan_api`, `philadelphia_api`, `asian_art_sf`) |
| `search <query>` | `--top, -k` 结果数 (默认 5)<br>`--graph/--no-graph` 图谱搜索 (默认 on)<br>`--max-hops, -h` 最大跳数 (默认 2)<br>`--vector-weight` 向量权重 (默认 0.4)<br>`--bm25-weight` BM25 权重 (默认 0.3)<br>`--graph-weight` 图谱权重 (默认 0.3) | 混合检索 (向量+BM25+图谱) |
| `ingest csv` | `--data-dir, -d` CSV 目录<br>`--adapter, -a` 适配器 (philamuseum / philamuseum_raw)<br>`--ingest/--no-ingest` 是否同时提取文档<br>`--llm/--no-llm` LLM 三元组提取<br>`--dedup` 去重阈值 (默认 0.95) | 从 CSV 导入文物原始数据 |
| `ingest artifacts` | `--museum, -m` 按博物馆筛选<br>`--limit, -n` 最大数量<br>`--llm/--no-llm` LLM 三元组提取<br>`--skip-ingested/--no-skip-ingested` 跳过已摄入<br>`--dedup` 去重阈值 (默认 0.95) | 从文物表提取文档到 DocumentTable |
| `check-similar <content>` | `--threshold, -t` 相似度阈值 (默认 0.95)<br>`--top, -n` 最大结果数 (默认 5) | 检查文档相似度 |
| `python -m knowgraph.migration.migrate_to_mysql` | `--dry-run` `--limit N` `--clean` | 图数据库 → MySQL 迁移 |
| `python -m knowgraph.migration.migrate_to_neo4j` | `--dry-run` `--limit N` `--clean` | 三元组 → Neo4j 迁移 |

### just 快捷命令

| 命令 | 说明 |
|------|------|
| `just web` | 启动后端服务器 |
| `just ui` | 启动前端开发服务器 |
| `just initdb` | 初始化数据库 |
| `just database` | 启动数据库容器 |
| `just docker` | 启动所有容器 |
| `just build-ui` | 构建前端并同步到 static/ |
| `just migrate-mysql <opts>` | 图数据库 → MySQL 迁移，不加参数全量（`--dry-run` `--limit N` `--clean`） |
| `just migrate-neo4j <opts>` | 三元组 → Neo4j 迁移，不加参数全量（`--dry-run` `--limit N` `--clean`） |

### 开发命令

| 命令 | 说明 |
|------|------|
| `cd backend && pytest` | 运行后端测试 |
| `cd backend && ruff check knowgraph/` | 代码检查 |
| `cd backend && ty check knowgraph/` | 类型检查 |

## 已支持的博物馆

| 博物馆 | 爬取模式 | 说明 |
|--------|----------|------|
| Cleveland Museum of Art | 网站地图 | 克利夫兰艺术博物馆 |
| Metropolitan Museum of Art | 网站地图 + 适配器 API | 大都会艺术博物馆 (`metropolitan` / `metropolitan_api`) |
| Smithsonian Institution | 网站地图 | 史密森尼学会 |
| Freer+Sackler Galleries | 网站地图 | 弗利尔+赛克勒美术馆 |
| Princeton University Art Museum | 网站地图 | 普林斯顿大学艺术博物馆 |
| Nelson-Atkins Museum of Art | 网站地图 | 纳尔逊-阿特金斯艺术博物馆 |
| Art Institute of Chicago | 网站地图 | 芝加哥艺术博物馆 |
| Philadelphia Museum of Art | 网站地图 + 适配器 API | 费城艺术博物馆 (`philadelphia` / `philadelphia_api`) |
| American Museum of Natural History | 网站地图 | 美国自然历史博物馆 |
| Asian Art Museum of San Francisco | 适配器 (Playwright) | 旧金山亚洲艺术博物馆 (`asian_art_sf`) |

## 环境变量

优先级：**环境变量 > 项目根目录 `.env` 文件 > 类默认值**。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FASTAPI_HOST` | `127.0.0.1` | 后端监听地址 |
| `FASTAPI_PORT` | `40001` | 后端端口 |
| `RELEASE_MODE` | `True` | 发布模式开关 |
| `JWT_SECRET` | `knowgraph-jwt-secret-...` | JWT 密钥 |
| `RAG_TOKEN_EXPIRES_IN` | `21600` | JWT 过期时间（秒） |
| `POSTGRES_HOST` | `127.0.0.1` | PostgreSQL / AGE 图数据库主机 |
| `POSTGRES_PORT` | `10004` | 图数据库端口 |
| `POSTGRES_USER` | `postgres` | 图数据库用户 |
| `POSTGRES_DB` | `data` | 图数据库名 |
| `POSTGRES_PASSWORD` | `postgres_password` | 图数据库密码 |
| `AGE_GRAPH_NAME` | `graph` | Apache AGE 图名称 |
| `MYSQL_HOST` | `127.0.0.1` | MySQL 迁移目标主机 |
| `MYSQL_PORT` | `13306` | MySQL 端口 |
| `MYSQL_DATABASE` | `seitem` | MySQL 数据库名 |
| `MYSQL_USER` | `seitem` | MySQL 用户 |
| `MYSQL_PASSWORD` | `seitem123456` | MySQL 密码 |
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Neo4j 迁移目标 Bolt 地址 |
| `NEO4J_USER` | `neo4j` | Neo4j 用户 |
| `NEO4J_PASSWORD` | `neo4j123456` | Neo4j 密码 |

## 许可证

本项目未明确许可证。
