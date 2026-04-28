# 海外中国文物知识图谱构建系统 - 开发任务清单

## 项目背景

本项目旨在构建海外中国文物知识图谱系统，为文物知识问答子系统提供数据支撑。MCP 服务将为问答子系统提供 RAG 和知识图谱查询能力。

---

## 一、知识图谱模块

### 1.1 Apache AGE 图数据库集成
- [ ] 安装 apache-age-python 依赖
- [ ] 实现在knowgraph/database/graph.py 实现三元组存储接口（增删改查）
- [ ] 实现 SPARQL/Cypher 查询接口

### 1.2 CIDOC-CRM 本体建模
- [ ] 创建 knowgraph/graph/schema.py
- [ ] 定义实体类型：Artifact、Museum、Dynasty、Artist、Location
- [ ] 定义关系类型：收藏于、创作于、属于朝代、材质为、类型为
- [ ] 实现实体 URI 生成策略

### 1.3 三元组管理
- [ ] 创建 knowgraph/graph/triples.py
- [ ] 实现三元组数据模型
- [ ] 实现与清洗后数据的映射逻辑
- [ ] 实现增量更新机制
- [ ] 实现使用llm结构化输出从爬虫爬取的页面内容提取三元组和描述（暂时假定为csv按行输入作为不同博物馆，通过llm提取三元组）

---

## 二、RAG 升级为 GraphRAG

### 2.1 图增强索引
- [ ] 添加图apacheage数据库管理类，其内有关图插入，删除，检索等
- [ ] 修改 knowgraph/database/ragmode.py
- [ ] 新增实体节点索引通道
- [ ] 新增关系边索引通道
- [ ] 实现图结构与向量索引的同步更新

### 2.2 混合搜索增强
- [ ] 修改 RRF 算法，添加图打分通道
- [ ] 实现 vector + BM25 + graph 三通道融合
- [ ] 添加图关系权重配置
- [ ] 优化搜索性能

### 2.3 图感知检索
- [ ] 实现基于图结构的上下文扩展
- [ ] 支持多跳关系检索
- [ ] 支持实体路径查询

---

## 三、MCP 服务

### 3.1 MCP Server 基础设施
- [ ] 安装 fastmcp 依赖 
- [ ] 创建 knowgraph/api/mcp-server.py - MCP Server 主入口，挂载在fastapi主程序中
- [ ] 实现工具注册与路由机制

### 3.2 MCP 工具定义
- [ ] 创建 knowgraph/mcp/tools.py
- [ ] 实现知识库搜索工具 (search_rag)
- [ ] 实现知识图谱查询工具 (query_graph)
- [ ] 实现三元组检索工具 (get_triples)
- [ ] 实现实体信息查询工具 (get_entity)

---

## 四、工具函数与辅助模块

### 4.1 prompt 模板扩充
- [ ] 创建 knowgraph/utils/prompts.py - 文物领域专用 prompt
- [ ] 添加 GraphRAG 查询模板
- [ ] 添加实体识别 prompt
- [ ] 添加关系推理 prompt

### 4.2 配置管理
- [ ] 更新 pyproject.toml 添加依赖（apache-age, fastmcp）
- [ ] 更新 .gitignore
- [ ] 添加环境变量配置示例

---

## 五、测试与文档

### 5.1 单元测试
- [ ] 为 knowledge_graph 模块编写测试
- [ ] 为 GraphRAG 混合搜索编写测试
- [ ] 为 MCP 工具编写测试

### 5.2 文档
- [ ] 更新 README.md - 添加 MCP 服务说明
- [ ] 更新 README.md - 添加 GraphRAG 说明
- [ ] 添加 API 文档

## 六，清理无用代码

---


## 备注

- 文物问答子系统由他人完成，不在本清单范围内
- MCP 服务主要为问答子系统提供 RAG 和知识图谱查询能力
- GraphRAG 需在 RRF 融合中增加图打分通道，实现 vector + BM25 + graph 三通道混合搜索
