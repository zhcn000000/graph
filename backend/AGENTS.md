# KnowGraph Backend

## 项目概览

后端是一个基于 FastAPI 的知识图谱 + RAG (检索增强生成) 系统,支持向量检索和图谱查询。

**技术栈**: FastAPI, pydantic-ai, SQLModel, PostgreSQL/AGE 图数据库, FastMCP

## 项目结构

```
backend/
├── knowgraph/
│   ├── __init__.py           # 公共导出
│   ├── routers/              # FastAPI 路由
│   │   ├── chat.py           # 聊天 API (SSE 流式响应)
│   │   ├── rag.py            # RAG + 图谱操作 API
│   │   └── __init__.py       # 合并路由到主 app
│   ├── chat/                 # AI Agent 模块
│   │   ├── model.py          # pydantic_ai Agent 定义
│   │   ├── chat_model.py     # 模型配置获取
│   │   ├── rag_tool.py       # RAG 工具集
│   │   ├── code_tool.py      # 代码工具
│   │   └── struct.py         # ModelDeps, ToolEnum 等数据结构
│   ├── database/             # 数据库层
│   │   ├── database.py       # DatabaseManager (SQLModel)
│   │   ├── graph.py          # AgeGraphManager (图数据库)
│   │   ├── ragmode.py        # RAGMode (检索+图谱混合搜索)
│   │   ├── rag.py            # RAGConfig 配置管理
│   │   ├── history.py        # HistoryStore 会话历史
│   │   ├── source.py         # SourceStore 文档来源
│   │   ├── document.py       # DocumentStore 文档管理
│   │   ├── pool.py           # ConnectionPoolManager 连接池
│   │   ├── tables.py         # SQLModel 表定义
│   │   └── types.py          # 类型定义 (BM25Vector 等)
│   ├── graph/                # 知识图谱模块
│   │   ├── triples.py        # LLMExtractor 三元组提取
│   │   ├── edge_strength.py  # EdgeStrengthCalculator 边强度计算
│   │   └── schema.py         # EntityType 等图谱结构
│   ├── documents/            # 文档处理管道
│   │   ├── converter.py      # 文件格式转换 (aload_documents)
│   │   ├── splitter.py       # 文本分片 (asplit_content)
│   │   ├── tokenizer.py      # Tokenization (atokenize_content)
│   │   ├── embedder.py       # 向量嵌入 (aembed_documents)
│   │   └── models.py        # Document 数据模型
│   ├── utils/
│   │   ├── environments.py   # 环境变量
│   │   ├── file.py          # FileStream 文件处理
│   │   ├── templete.py      # Prompt 模板
│   │   └── prompts.py       # Prompt 工具函数
│   └── mcp/
│       └── tools.py          # FastMCP 工具定义 (MCP 协议)
└── pyproject.toml            # 项目配置 (Python 3.14, ruff, typ)
```

## 核心模块

### 1. Routers (API 入口)

**chat.py** - 聊天路由 `/chat`

- `POST /{session_id}/stream` - SSE 流式聊天
- `GET /{session_id}/history` - 获取历史消息
- `POST /title` - 生成会话标题
- `POST /` - 创建会话
- `DELETE /{session_id}` - 删除会话
- `PATCH /{session_id}` - 重命名会话
- `GET /list` - 会话列表

**rag.py** - RAG 路由 `/rag`

- RAG 知识库 CRUD: 创建/列表/获取/更新/删除
- 文件上传/删除
- 搜索: `/rag/{rag_id}/search`
- 图操作: `/rag/graph/vertex`, `/rag/graph/edge`, `/rag/graph/search` 等

### 2. Chat (Agent 系统)

使用 `pydantic_ai` 构建 AI Agent:

- `model.py`: 定义 `agent` 和动态指令函数 `metadata_prompt`, `rag_prompt`
- 支持流式输出 (SSE)
- 工具集: `rag_toolkit` 等

### 3. Database (数据层)

- **DatabaseManager**: SQLModel ORM, PostgreSQL
- **AgeGraphManager**: Apache AGE 图数据库
- **RAGMode**: 核心检索类,混合向量+图搜索
- **HistoryStore**: 会话历史存储
- **ConnectionPoolManager**: 连接池管理

### 4. Graph (知识图谱)

- **LLMExtractor**: 从文档提取三元组 (subject-predicate-object)
- **EdgeStrengthCalculator**: 计算边权重
- **EntityType**: 实体类型定义

### 5. Documents (文档处理)

完整管道: 文件 → 转换 → 分片 → Tokenize → 向量化 → 存储

### 6. MCP (Model Context Protocol)

FastMCP 工具,暴露图谱能力给外部 LLM 调用

## 入口

`knowgraph/routers/__init__.py` 创建 FastAPI app,合并:

- `/mcp` - MCP 协议端点
- `/chat` - 聊天 API
- `/rag` - RAG API

## 开发命令

```bash
# Lint
ruff check knowgraph/

# Type check
ty check knowgraph/

# Format
ruff format knowgraph/
```

## 依赖

- FastAPI, Starlette
- pydantic-ai (AI Agent)
- SQLModel, sqlalchemy
- postgresql + apache-age
- fastmcp
- orjson

## 其他

- 尽量在模块顶部导入包
- 尽量使用sqlalchemy的ddl构建器构建stmt执行，除非无法构建
- python版本为3.14,具有类型系统改进,因此使用`from __future__ import annotations`导入是不必要的
