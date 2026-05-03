# KnowGraph Backend

## 项目概览

后端是基于 FastAPI 的知识图谱 + RAG (检索增强生成) 系统,支持向量检索、BM25 检索和图谱查询的混合搜索。

**技术栈**: FastAPI, pydantic-ai, SQLModel, PostgreSQL/AGE 图数据库, FastMCP, Scrapy

## 项目结构

```
backend/
├── knowgraph/
│   ├── __init__.py              # 公共导出
│   ├── __main__.py              # CLI 入口
│   ├── routers/                 # FastAPI 路由
│   │   ├── __init__.py          # FastAPI app 创建,挂载 MCP
│   │   ├── chat.py              # 聊天 API (SSE 流式响应)
│   │   └── rag.py               # RAG + 图谱操作 API
│   ├── chat/                    # AI Agent 模块
│   │   ├── __init__.py          # 导出 agent, get_model, rag_toolset, ModelDeps
│   │   ├── model.py             # pydantic_ai Agent 定义
│   │   ├── chat_model.py        # 模型配置获取
│   │   ├── tools.py             # Agent 工具集 (FunctionToolset)
│   │   └── struct.py            # ModelDeps 数据结构
│   ├── database/                # 数据库层
│   │   ├── __init__.py          # 导出所有数据库组件
│   │   ├── database.py          # DatabaseManager (SQLModel/PostgreSQL)
│   │   ├── graph.py             # AgeGraphManager (AGE 图数据库)
│   │   ├── ragmode.py           # RAGMode 核心检索类 (混合向量+BM25+图搜索)
│   │   ├── pool.py              # ConnectionPoolManager 连接池
│   │   ├── history.py           # HistoryStore 会话历史
│   │   ├── source.py            # SourceStore 文档来源
│   │   ├── document.py          # DocumentStore 文档管理
│   │   ├── artifact.py          # ArtifactStore 文物原始数据
│   │   ├── tables.py            # SQLModel 表定义
│   │   └── types.py             # 类型定义 (BM25Vector 等)
│   ├── graph/                   # 知识图谱模块
│   │   ├── __init__.py          # 导出图谱组件
│   │   ├── triples.py           # LLMExtractor 三元组提取, CSVRowInput
│   │   ├── edge_strength.py     # EdgeStrengthCalculator 边强度计算
│   │   └── schema.py            # EntityType, RelationshipType 等本体定义
│   ├── documents/               # 文档处理管道
│   │   ├── __init__.py          # 导出 Document, 文档处理函数
│   │   ├── models.py            # Document 数据模型
│   │   ├── splitter.py          # 文本分片 (asplit_content)
│   │   ├── tokenizer.py         # BM25 Tokenization (atokenize_content)
│   │   └── embedder.py          # 向量嵌入 (aembed_documents, arerank_documents)
│   ├── spider/                  # Web 爬虫模块
│   │   ├── __init__.py          # 导出爬虫组件
│   │   ├── spider.py            # ArtifactSitemapSpider 博物馆文物爬虫
│   │   ├── models.py            # SitemapUrl, ArtifactData, CrawlResult
│   │   ├── pipeline.py          # ArtifactPipeline 数据管道
│   │   ├── runner.py            # 爬虫运行器
│   │   ├── config.py            # MuseumConfig 博物馆配置
│   │   └── filter.py            # ChineseArtifactFilter 中文文物过滤
│   ├── tools/                   # 工具模块
│   │   ├── __init__.py          # 导出工具
│   │   ├── base.py              # 工具基类实现 (search_documents_base 等)
│   │   └── mcp.py               # FastMCP 工具定义 (MCP 协议)
│   └── utils/
│       ├── __init__.py          # 导出工具函数
│       ├── environments.py      # 环境变量
│       ├── templete.py          # Prompt 模板
│       └── prompts.py           # Prompt 工具函数
└── pyproject.toml               # 项目配置 (Python 3.14, ruff, typ)
```

## 核心模块

### 1. Routers (API 入口)

**chat.py** - 聊天路由 `/chat`

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/{session_id}/stream` | SSE 流式聊天 |
| GET | `/{session_id}/history` | 获取历史消息 |
| POST | `/title` | 生成会话标题 |
| POST | `/` | 创建会话 |
| DELETE | `/{session_id}` | 删除会话 |
| PATCH | `/{session_id}` | 重命名会话 |
| GET | `/list` | 会话列表 |

**rag.py** - RAG 路由 `/rag`

- 搜索: `POST /search` - 混合检索 (向量+BM25+图)
- 图操作:
  - `POST/GET/PUT/DELETE /graph/vertex/{uri}` - 节点 CRUD
  - `POST/GET/DELETE /graph/edge/{start_uri}/{end_uri}` - 边 CRUD
  - `GET /graph/neighbors/{uri}` - 获取邻居节点
  - `GET /graph/traverse/{start_uri}` - 图遍历
  - `POST /graph/traverse/multi` - 批量遍历
  - `GET /graph/paths/{start_uri}/{end_uri}` - 路径查询
  - `POST /graph/context` - 图上下文扩展
  - `POST /graph/entity-paths` - 实体路径查询

### 2. Chat (Agent 系统)

使用 `pydantic_ai` 构建 AI Agent (`knowgraph/chat/model.py`):

```python
agent: Agent[ModelDeps, str] = Agent(
    model=get_model(),
    deps_type=ModelDeps,
    toolsets=[rag_toolset],
    instructions=FIRST_INPUT_TEMPLATE,
    output_retries=5,
)
```

**工具集** (`knowgraph/chat/tools.py`):

- `search_documents` - 文档搜索
- `traverse_graph` - 图谱遍历
- `get_entity_info` - 获取实体信息
- `get_entity_paths` - 查询实体路径
- `get_document_context` - 获取文档上下文
- `get_document_entities` - 获取文档关联实体
- `python_repl` - Python 代码执行

### 3. Database (数据层)

- **DatabaseManager** (`database.py`): SQLModel ORM, PostgreSQL 连接管理
- **AgeGraphManager** (`graph.py`): Apache AGE 图数据库操作,支持:
  - 节点/边的 CRUD
  - 图遍历 (traverse, traverse_multi)
  - 路径查询 (find_paths, find_entity_paths)
  - NetworkX 互转 (afrom_networkx, ato_networkx)
- **RAGMode** (`ragmode.py`): 核心检索类,混合搜索策略:
  - `_vector_search`: pgvector 向量相似度检索
  - `_bm25_search`: BM25 全文检索
  - `_graph_search`: 图谱 PageRank + 边强度检索
  - `_rrf_fusion`: RRF (Reciprocal Rank Fusion) 融合
  - `ahyprid_search`: 完整混合检索流程
- **HistoryStore** (`history.py`): 会话历史存储
- **SourceStore** (`source.py`): 文档来源管理
- **ArtifactStore** (`artifact.py`): 文物原始数据存储
- **ConnectionPoolManager** (`pool.py`): 连接池管理

### 4. Graph (知识图谱)

**本体模型** (`knowgraph/graph/schema.py`):
- **实体类型** (EntityType): ARTIFACT, MUSEUM, DYNASTY, ARTIST, LOCATION, MATERIAL, ARTIFACT_TYPE
- **关系类型** (RelationshipType): COLLECTED_BY, CREATED_BY, BELONGS_TO_DYNASTY, MADE_OF_MATERIAL, IS_TYPE_OF, LOCATED_AT, DEPICTS, RELATED_TO
- CIDOC_GRAPH: CIDOC-CRM 本体标准

**三元组提取** (`knowgraph/graph/triples.py`):
- `LLMExtractor`: 从文物记录中用 LLM 提取三元组
- `CSVRowInput`: CSV 行数据模型,自动转换为 ArtifactTriple 等
- `ArtifactTriple`: 文物到博物馆的收藏关系三元组

**边强度计算** (`knowgraph/graph/edge_strength.py`):
- `EdgeStrengthCalculator`: 计算边的关联强度
- `TripleBasedEdgeQuerier`: 基于实体名查询边

### 5. Documents (文档处理管道)

```
文件 → 转换 → 分片 → Tokenize → 向量化 → 存储
```

- `Document` 模型: 文档数据模型
- `asplit_content`: 文本分片 (chunk_size=512, overlap=64)
- `atokenize_content`: BM25 分词
- `aembed_documents`: 向量嵌入
- `arerank_documents`: 重排序

### 6. Spider (爬虫模块)

- `ArtifactSitemapSpider`: 基于 Scrapy SitemapSpider 的博物馆文物爬虫
- `ArtifactPipeline`: 异步存储文物数据到数据库
- `ChineseArtifactFilter`: 过滤与中国无关的文物
- `MuseumConfig`: 博物馆配置 (sitemap_url, artifact_url_patterns 等)
- `ArtifactData`: 文物数据模型

### 7. Tools (MCP 协议)

**FastMCP** (`knowgraph/tools/mcp.py`):
- 暴露图谱能力给外部 LLM 调用
- 与 Agent 工具集共享 base 实现

**Base Tools** (`knowgraph/tools/base.py`):
- `search_documents_base`
- `traverse_graph_base`
- `get_entity_info_base`
- `get_entity_paths_base`
- `get_document_context_base`
- `get_document_entities_base`
- `python_repl_base` (基于 pydantic-monty 沙盒执行)

## 入口

`knowgraph/routers/__init__.py`:

```python
mcp_app = mcp.http_app()
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)      # MCP 协议端点
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(rag_router, prefix="/rag", tags=["rag"])
```

## 开发命令

```bash
# Lint
ruff check knowgraph/

# Type check
ty check knowgraph/

# Format
ruff format knowgraph/

# Run tests
pytest

# CLI
knowgraph --help
```

## 依赖

- **Web**: FastAPI, Starlette, uvicorn
- **AI Agent**: pydantic-ai
- **Database**: SQLModel, sqlalchemy, psycopg, asyncpg, pgvector
- **Graph**: apache-age-python (Apache AGE)
- **Search**: networkx (图算法), scipy (PageRank)
- **Documents**: transformers (嵌入模型)
- **Spider**: scrapy, beautifulsoup4, lxml
- **MCP**: fastmcp
- **Utils**: orjson, rich, pydantic-monty (Python REPL)

## 环境变量

参见 `knowgraph/utils/environments.py`:

| 变量 | 描述 | 默认值 |
|------|------|--------|
| POSTGRES_DB | PostgreSQL 数据库名 | data |
| POSTGRES_HOST | 数据库主机 | localhost |
| POSTGRES_PORT | 数据库端口 | 5432 |
| POSTGRES_USER | 数据库用户 | - |
| POSTGRES_PASSWORD | 数据库密码 | - |

## 数据库表

- `SessionTable`: 会话表
- `HistoryTable`: 历史消息表
- `Source`: 文档来源表
- `DocumentTable`: 文档分块表 (含 vector, bmvector, entities)
- `ArtifactRawTable`: 文物原始数据表

## 注意事项

- 使用 `from __future__ import annotations` 在模块顶部是**不必要的** (Python 3.14)
- 尽量使用 sqlalchemy 的 DDL 构建器构建 stmt 执行,除非无法构建
- 工具函数同时存在于 `chat/tools.py` (Agent FunctionToolset) 和 `tools/mcp.py` (FastMCP)
- Spider 模块用于从博物馆网站爬取文物数据并导入图谱