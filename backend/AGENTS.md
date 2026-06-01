# KnowGraph Backend

## 项目概览

后端是基于 FastAPI 的知识图谱 + RAG (检索增强生成) 系统,支持向量检索、BM25 检索和图谱查询的混合搜索。专注海外中国文物知识管理。

**技术栈**: FastAPI, pydantic-ai, SQLModel, PostgreSQL/vchord+AGE, FastMCP, Scrapy, curl_cffi

## 项目结构

```
backend/
├── knowgraph/
│   ├── __init__.py              # 导出 app (FastAPI)
│   ├── __main__.py              # CLI 入口 (uvicorn, 数据库, 爬虫)
│   ├── routers/                 # FastAPI 路由
│   │   ├── __init__.py          # FastAPI app 创建,挂载 MCP
│   │   ├── chat.py              # 聊天 API (SSE 流式响应)
│   │   ├── rag.py               # RAG + 图谱操作 + 文档摄入 API
│   │   └── user.py              # 用户认证 API (JWT)
│   ├── chat/                    # AI Agent 模块
│   │   ├── __init__.py          # (空)
│   │   ├── model.py             # pydantic_ai Agent 定义 (OpenAIChatModel+DeepSeek)
│   │   ├── struct.py            # ModelDeps 数据结构 (select_toolset)
│   │   └── tools.py             # Agent 工具集 (3个 FunctionToolset)
│   ├── database/                # 数据库层
│   │   ├── __init__.py          # 导出 User, UserManager, init/clean/reset_db
│   │   ├── database.py          # DatabaseManager (SQLModel/PostgreSQL)
│   │   ├── graph.py             # AgeGraphManager (AGE 图数据库)
│   │   ├── ragmode.py           # RAGMode 核心检索类 (混合向量+BM25+图搜索)
│   │   ├── pool.py              # ConnectionPoolManager 连接池
│   │   ├── cypherbuild.py       # Fluent Cypher 查询构建器 (Apache AGE)
│   │   ├── tables.py            # SQLModel 表定义
│   │   ├── types.py             # 类型定义 (BM25Vector, AGType, Password)
│   │   ├── initdb.py            # 数据库初始化 (扩展, AGE 图, 建表)
│   │   ├── user.py              # UserManager (JWT 认证)
│   │   ├── history.py           # HistoryStore 会话历史
│   │   ├── source.py            # SourceStore 文档来源
│   │   ├── document.py          # DocumentStore 文档管理 (含 LLM 三元组提取)
│   │   └── artifact.py          # ArtifactStore 文物原始数据
│   ├── graph/                   # 知识图谱模块
│   │   ├── __init__.py          # 导出图谱组件
│   │   ├── schema.py            # EntityType, RelationshipType, ExtractedEntity 等本体
│   │   └── triples.py           # LLMExtractor 三元组提取
│   ├── documents/               # 文档处理管道
│   │   ├── __init__.py          # (空)
│   │   ├── models.py            # Document 数据模型 + spacy NLP
│   │   ├── converter.py         # 文件转换 (MarkItDown)
│   │   ├── splitter.py          # 文本分片 (asplit_content, spacy 分句)
│   │   ├── tokenizer.py         # BM25 Tokenization (mmh3 hash)
│   │   └── embedder.py          # 向量嵌入和重排序 (SiliconFlow API)
│   ├── spider/                  # Web 爬虫模块
│   │   ├── __init__.py          # 导出爬虫组件
│   │   ├── spider.py            # ArtifactSitemapSpider 博物馆文物爬虫
│   │   ├── models.py            # SitemapUrl, ArtifactData, CrawlResult
│   │   ├── pipeline.py          # ArtifactPipeline 数据管道
│   │   ├── runner.py            # ScrapyCrawler 爬虫运行器
│   │   ├── config.py            # MuseumConfig 博物馆配置 (7个博物馆)
│   │   ├── filter.py            # ChineseArtifactFilter 中文文物过滤
│   │   └── download.py          # DownloadMiddleware (curl_cffi 浏览器指纹)
│   ├── tools/                   # 工具模块
│   │   ├── __init__.py          # (空)
│   │   ├── base.py              # 工具基类实现 (含 web 搜索/爬虫/代码执行)
│   │   └── mcp.py               # FastMCP 工具定义 (MCP 协议)
│   └── utils/
│       ├── __init__.py          # 导出工具函数
│       ├── environments.py      # 环境变量 (pydantic-settings)
│       ├── templete.py          # Agent Prompt 模板
│       └── prompts.py           # Graph/RAG Prompt 模板
├── tests/                       # 测试
│   ├── conftest.py
│   ├── test_converter.py
│   ├── test_graph.py
│   ├── test_rag.py
│   ├── test_schema.py
│   ├── test_search.py
│   └── test_triples.py
└── pyproject.toml               # 项目配置 (Python 3.14, ruff, ty)
```

## 核心模块

### 1. Routers (API 入口)

**`routers/__init__.py`** - FastAPI app 创建,挂载 MCP (/mcp), 注册 chat/rag/user 路由

**chat.py** - 聊天路由 `/chat`

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/{session_id}/stream` | SSE 流式聊天 (支持思考/工具调用) |
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
  - `POST/GET/DELETE /graph/edge/{start_uri}/{end_uri}[/{relationship_type}]` - 边 CRUD
  - `GET /graph/neighbors/{uri}` - 获取邻居节点
  - `GET /graph/traverse/{start_uri}` - 图遍历
  - `POST /graph/traverse/multi` - 批量遍历
  - `GET /graph/paths/{start_uri}/{end_uri}` - 路径查询
  - `POST /graph/context` - 图上下文扩展
  - `POST /graph/entity-paths` - 实体路径查询
- 文档摄入:
  - `POST /documents/upload` - 上传文档
  - `POST /documents/load-csv` - 加载 CSV
  - `POST /documents/ingest-artifacts` - 从文物表提取文档

**user.py** - 用户认证 `/api`, 用户管理 `/users`

- `POST /api/login` - 登录
- `POST /api/register` - 注册
- `POST /api/refresh` - 刷新 token
- `GET /users/me` - 当前用户
- `GET/PATCH/DELETE /users/{user_id}` - 用户 CRUD

### 2. Chat (Agent 系统)

使用 `pydantic_ai` 构建 AI Agent (`knowgraph/chat/model.py`):

```python
agent: Agent[ModelDeps, str] = Agent(
    model=OpenAIChatModel(model_name="deepseek-v4-flash", provider=DeepSeekProvider()),
    deps_type=ModelDeps,
    toolsets=[rag_toolset, code_toolset, web_toolset],
    instructions=FIRST_INPUT_TEMPLATE,
    output_retries=5,
)
```

**支持动态指令注入**: `@agent.instructions` 注入模型名称和当前时间

**工具集** (`knowgraph/chat/tools.py`) — 3 个可选的 FunctionToolset:

- **rag_toolkit**: `search_documents`, `traverse_graph`, `get_entity_info`, `get_entity_paths`, `get_document_context`, `get_document_entities`
- **code_toolkit**: `python_repl` (基于 pydantic-monty 沙盒)
- **web_toolkit**: `search_web`, `extract_web`, `crawl_web`, `fetch_web` (基于 Tavily + httpx + BeautifulSoup)

通过 `ModelDeps.select_toolset` 动态控制可用工具集。每个工具使用 `prepare` 回调控制是否暴露。

### 3. Database (数据层)

- **DatabaseManager** (`database.py`): SQLModel ORM, PostgreSQL 连接管理, 支持 sync/async session, connection, cursor
- **AgeGraphManager** (`graph.py`): Apache AGE 图数据库操作,支持:
  - 节点/边的 CRUD (upsert via MERGE)
  - 图遍历 (traverse, traverse_multi) 支持方向/跳数
  - 路径查询 (find_paths, find_entity_paths)
  - 上下文扩展 (aexpand_context)
  - NetworkX 互转 (afrom_networkx, ato_networkx)
  - 边连接查询 (aget_all_edge_connections, aquery_edge_connections)
- **CypherBuilder** (`cypherbuild.py`): Fluent 链式 Cypher 查询构建器
  - `PatternBuilder`: 节点/边模式构建
  - `FunctionBuilder`: 函数调用构建
  - `ExpressionBuilder`: 表达式构建 (支持运算符重载)
  - `CypherBuilder`: MATCH/MERGE/CREATE/SET/DELETE/WHERE/RETURN 等
- **RAGMode** (`ragmode.py`): 核心检索类,混合搜索策略:
  - `_vector_search`: vchord 向量相似度检索 (cosine via `<#`)
  - `_bm25_search`: vchord_bm25 全文检索
  - `_graph_search`: 图谱 PageRank + 边强度检索
  - `_graph_pagerank`: NetworkX PageRank 算法, EgoGraph 子图
  - `_rrf_fusion`: RRF (Reciprocal Rank Fusion) 融合
  - `ahyprid_search`: 完整混合检索流程 (查询→向量+BM25→图→RRF→重排序)
  - `aquery_graph_context`: 查询驱动的图谱上下文
- **initdb.py**: `init_db`/`clean_db`/`reset_db`, 创建 pgcrypto/vchord/vchord_bm25/age 扩展
- **user.py**: `UserManager` — JWT 认证 (HS256), 用户 CRUD
- **HistoryStore** (`history.py`): 会话历史存储 (JSONB), 使用 uuid_extract_timestamp 排序
- **SourceStore** (`source.py`): 文档来源管理
- **DocumentStore** (`document.py`): 文档管理, LLM 三元组提取, NetworkX 图同步, 双级分块 (4096→512)
- **ArtifactStore** (`artifact.py`): 文物原始数据 CRUD
- **ConnectionPoolManager** (`pool.py`): psycopg 同步/异步连接池, 注册 vector/bit/halfvec/sparsevec/hstore/geometry/agtype/bm25vector 类型适配器

### 4. Graph (知识图谱)

**本体模型** (`knowgraph/graph/schema.py`):
- **实体类型** (EntityType): ARTIFACT, MUSEUM, DYNASTY, ARTIST, LOCATION, MATERIAL, ARTIFACT_TYPE
- **关系类型** (RelationshipType): COLLECTED_BY, CREATED_BY, BELONGS_TO_DYNASTY, MADE_OF_MATERIAL, IS_TYPE_OF, LOCATED_AT, DEPICTS, RELATED_TO
- **URI 格式**: `cidoc:{entity_type}/{safe_name}`
- `ExtractedEntity` / `ExtractedTriple`: 提取的实体和三元组模型
- `RelationshipInfo`: 含 strength 字段

**三元组提取** (`knowgraph/graph/triples.py`):
- `LLMExtractor`: 从文物记录中用 LLM (复用 Agent) 提取三元组, 自动 web 搜索补充
- CSV 数据通过 `knowgraph/adapters/` 下的适配器读取，再写入 `ArtifactRawTable`
- `compute_triples_strength`: 用重排序打分计算边强度
- 支持 CSV 文件/DataFrame/单行/文档多种输入

### 5. Documents (文档处理管道)

```
文件 → MarkItDown 转换 → Document → 双级分块 → Embed (BAAI/bge-m3 API) → Tokenize (mmh3 hash) → 存储
```

- `Document` 模型: content, name, link, query_score, metadata, entities, triples, id, file_id, document_index, chunk_index
- `aconvert_file`: 文件/URL/Stream → Markdown (MarkItDown)
- `asplit_content`/`asplit_document`: spacy 中文分句, chunk_size=512/4096, overlap=32/128
- `atokenize_document`: mmh3 hash → Counter (BM25 词汇表 1M)
- `aembed_documents` / `arerank_documents`: SiliconFlow API (BAAI/bge-m3, BAAI/bge-reranker-v2-m3)

### 6. Spider (爬虫模块)

- `ArtifactSitemapSpider`: Scrapy SitemapSpider, 解析 JSON-LD/meta, 提取文物数据
- `DownloadMiddleware`: curl_cffi 浏览器指纹伪装 (chrome146)
- `ArtifactPipeline`: 异步存储文物到 ArtifactRawTable
- `ChineseArtifactFilter`: 中英文关键词/URL/文化分类过滤
- `MuseumConfig`: 7 个已配置博物馆 (Cleveland, Metropolitan, Smithsonian, Freer+Sackler, Princeton, Nelson-Atkins, Art Institute of Chicago, Philadelphia, AMNH)
- `ScrapyCrawler`: 异步爬虫运行器 (AsyncCrawlerProcess)

### 7. Tools (MCP 协议 + Agent 共享实现)

**FastMCP** (`knowgraph/tools/mcp.py`):
- 暴露 10 个工具给外部 LLM 调用 (search_documents, traverse_graph, get_entity_info, get_entity_paths, get_document_context, get_document_entities, python_repl, search_web, extract_web, crawl_web, fetch_web)
- 通过 `mcp.http_app()` 挂载到 FastAPI 的 `/mcp` 路径

**Base Tools** (`knowgraph/tools/base.py`):
- 所有工具共享 base 实现, 返回 Markdown 格式
- 使用 pandas DataFrame.to_markdown() 格式化表格
- Tavily: search_web, extract_web, crawl_web
- httpx + BeautifulSoup: fetch_web
- pydantic-monty: python_repl (沙盒执行)

## 入口

`knowgraph/routers/__init__.py`:

```python
mcp_app = mcp.http_app()
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)      # MCP 协议端点
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(rag_router, prefix="/rag", tags=["rag"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(user_router, prefix="/users", tags=["users"])
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

# Run server
knowgraph run-client

# Database init/reset/clean
knowgraph database init
knowgraph database reset
knowgraph database clean

# Spider
knowgraph spider cleveland metropolitan
```

## 依赖

- **Web**: FastAPI, Starlette, uvicorn, uvloop, httpx
- **AI Agent**: pydantic-ai, openai
- **Database**: SQLModel, sqlalchemy, psycopg, asyncpg, vchord, vchord_bm25
- **Graph**: apache-age-python (Apache AGE), networkx, scipy
- **Documents**: markitdown, spacy, zh-core-web-trf, mmh3
- **Embedding**: SiliconFlow API (BAAI/bge-m3), transformers (not directly used)
- **Spider**: scrapy, beautifulsoup4, lxml, curl-cffi
- **MCP**: fastmcp
- **Auth**: pyjwt
- **Search**: tavily-python
- **Utils**: orjson, rich, pydantic-monty, pandas, typer, asyncer

## 环境变量

参见 `knowgraph/utils/environments.py`:

| 变量 | 描述 | 默认值 |
|------|------|--------|
| FASTAPI_HOST | FastAPI 主机 | 127.0.0.1 |
| FASTAPI_PORT | FastAPI 端口 | 40001 |
| POSTGRES_DB | PostgreSQL 数据库名 | data |
| POSTGRES_HOST | 数据库主机 | 127.0.0.1 |
| POSTGRES_PORT | 数据库端口 | 40002 |
| POSTGRES_USER | 数据库用户 | postgres |
| POSTGRES_PASSWORD | 数据库密码 | postgres |
| POSTGRES_DSN | 自定义 DSN | - |
| DATA_ROOT | 数据根目录 | <project>/data |
| UUID_SEED | UUID 种子 | 11fa063e... |
| RELEASE_MODE | 发布模式 | True |
| TMP_DIR | 临时目录 | mkdtemp |
| TOKEN_EXPIRES_IN | JWT 过期秒数 | 21600 |
| JWT_SECRET | JWT 密钥 | knowgraph-jwt-secret... |
| SSL_KEY_PATH | SSL 密钥路径 | - |
| SSL_CERT_PATH | SSL 证书路径 | - |

## 数据库表

- `User`: 用户表 (含 password 列, Password 类型)
- `SessionTable`: 会话表
- `HistoryTable`: 历史消息表 (JSONB messages)
- `Source`: 文档来源表 (name, link, artifact_id FK)
- `DocumentTable`: 文档分块表 (vector ARRAY[Vector(1024)], bmvector, entities ARRAY, document_index, chunk_index, metadata JSONB)
  - vector 索引: vchordrq (vector_maxsim_ops)
  - bmvector 索引: bm25 (bm25_ops)
  - entities 索引: GIN
- `ArtifactRawTable`: 文物原始数据表 (detail_url 唯一)

## 注意事项

- 使用 `from __future__ import annotations` 在模块顶部是**不必要的**,为类型加引号保护同样是**不必要的** (Python 3.14)
- 尽量使用 sqlalchemy 的 DDL 构建器构建 stmt 执行,除非无法构建
- Agent 工具有三个 toolset (rag/code/web),通过 `ModelDeps.select_toolset` 控制
- 工具函数同时存在于 `chat/tools.py` (Agent FunctionToolset) 和 `tools/mcp.py` (FastMCP),共享 `tools/base.py` 实现
- Spider 使用 curl_cffi 浏览器指纹绕过 Cloudflare 保护
- 文档分块使用 spacy 中文分句,双级分块 (先 4096 再 512)
- 向量嵌入和重排序使用 SiliconFlow API,需设置 SILICONFLOW_API_KEY 环境变量
