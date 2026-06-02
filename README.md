# 海外藏中国文物知识图谱构建系统

从海外博物馆网站爬取中国文物信息，经过数据清洗、翻译、建模后存储到 MySQL 和 Neo4j，构建结构化的海外中国文物知识图谱。

## 系统架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  大都会博物馆  │     │  费城艺术博物馆 │     │ 旧金山亚洲艺术 │
│  (REST API)  │     │  (搜索 API)  │     │  (Selenium)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                    ┌─────────────┐
                    │  数据爬取     │  scrapers/
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │  数据清洗     │  cleaners/
                    │  朝代匹配/去重 │
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │  数据翻译     │  translators/
                    │ MyMemory/百度 │
                    └──────┬──────┘
                           ▼
              ┌────────────┴────────────┐
              ▼                         ▼
       ┌─────────────┐          ┌─────────────┐
       │   MySQL      │          │   Neo4j      │
       │  关系型存储    │          │  图谱存储     │
       └─────────────┘          └─────────────┘
              │                         │
              └────────────┬────────────┘
                           ▼
                    ┌─────────────┐
                    │  三元组建模   │  models/
                    │  RDF/CSV导出  │
                    └─────────────┘
```

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **开发语言** | Python 3.11 | 主开发语言 |
| **Web 爬虫** | requests + urllib3 | HTTP 请求，自动重试与会话管理 |
| | beautifulsoup4 + lxml | HTML 解析 |
| | Selenium | 无头浏览器爬取（旧金山亚洲艺术博物馆） |
| **数据处理** | pandas | CSV 读写、数据清洗与转换 |
| **关系数据库** | MySQL 8.0 | 结构化存储（35 张表），通过 PyMySQL 驱动连接 |
| **图数据库** | Neo4j 5.x (Community) | 知识图谱存储，通过官方 neo4j Python 驱动连接 |
| **翻译服务** | MyMemory API | 免费翻译源（主力） |
| | 百度翻译 API | 备用翻译源，质量更高 |
| **知识表示** | RDF / N-Triples | W3C 标准格式，支持链接开放数据（LOD）发布 |
| **容器化** | Docker + Docker Compose | 一键部署 MySQL + Neo4j + 应用 |

## 数据源

| 序号 | 博物馆 | API 类型 | 预估中国文物数量 |
|------|--------|----------|----------------|
| 2 | 大都会艺术博物馆 (Metropolitan Museum of Art) | 公开 REST API | ~9,700 件 |
| 7 | 旧金山亚洲艺术博物馆 (Asian Art Museum) | Selenium 爬取 / CSV 导入 | ~2,000 件 |
| 12 | 费城艺术博物馆 (Philadelphia Museum of Art) | 搜索 + 详情 API | ~6,200 件 |

## 知识图谱模型

### 节点类型

| 节点 | 说明 | 示例属性 |
|------|------|----------|
| `Artifact` | 文物 | object_id, title_en, title_zh, time_period |
| `Museum` | 博物馆 | name, country, city |
| `Dynasty` | 朝代 | name_en, name_zh, start_year, end_year |
| `Artist` | 艺术家 | name_en, name_zh |
| `Material` | 材质 | name |
| `ArtifactType` | 文物类型 | name |

### 关系类型

```
(Artifact) ──[:STORED_IN]──>        (Museum)
(Artifact) ──[:BELONGS_TO_DYNASTY]──> (Dynasty)
(Artifact) ──[:CREATED_BY]──>        (Artist)
(Artifact) ──[:MADE_OF]──>           (Material)
(Artifact) ──[:CLASSIFIED_AS]──>     (ArtifactType)
(Artifact) ──[:PRODUCED_IN]──>       (Location)
(Dynasty)  ──[:SUCCEEDED_BY]──>      (Dynasty)
```

## 快速开始

### Docker Compose

```bash
# 一键启动 MySQL + Neo4j + 应用
docker-compose up

# 仅启动数据库，本地运行爬虫
docker-compose up mysql neo4j
python main.py --step all
```

## 使用指南

### 环境依赖

```
uv sync
source ./.venv/bin/activate
```

### 命令行参数

```
python main.py --step <步骤> [--limit <数量>]
```

| 步骤 | 说明 |
|------|------|
| `all` | 执行全部流程（默认） |
| `crawl` | 仅数据爬取 |
| `clean` | 仅数据清洗 |
| `translate` | 仅数据翻译 |
| `mysql` | 仅写入 MySQL |
| `neo4j` | 仅写入 Neo4j |
| `triples` | 仅生成三元组 |

### 示例

```bash
# 全流程运行
python main.py --step all

# 每个博物馆只爬取 100 条（用于测试）
python main.py --step crawl --limit 100

# 爬取完成后单独执行清洗和翻译
python main.py --step clean
python main.py --step translate

# 将已清洗的数据写入数据库
python main.py --step mysql
python main.py --step neo4j
```

### 分步运行流程

```
crawl → clean → translate → mysql → neo4j → triples
爬取     清洗     翻译       存MySQL  存Neo4j  三元组
```

每一步都支持独立运行，中间结果保存在 `data/` 目录下的 CSV 文件中。

## 项目结构

```
KnowledgeGraph/
├── main.py                    # 主入口，流程编排
├── config.py                  # 全局配置（环境变量覆盖）
├── pyproject.toml             # 项目元数据与依赖声明
├── uv.lock                    # 依赖锁定文件（uv 生成）
├── Dockerfile                 # 应用容器镜像
├── docker-compose.yml         # MySQL + Neo4j + App 编排
│
├── sql/
│   └── init.sql               # MySQL 建表脚本（35 张表）
│
├── scrapers/                  # 数据爬取模块
│   ├── base.py                # 爬虫基类（重试/图片下载/断点续爬）
│   ├── met_museum.py          # 大都会博物馆（REST API）
│   ├── philamuseum.py         # 费城艺术博物馆（搜索 API）
│   └── asian_art_museum.py    # 旧金山亚洲艺术博物馆（Selenium/CSV 导入）
│
├── cleaners/                  # 数据清洗模块
│   └── cleaner.py             # 朝代匹配/字段标准化/去重
│
├── translators/               # 翻译模块
│   └── translator.py          # 双源翻译（MyMemory + 百度翻译）
│
├── storage/                   # 数据存储模块
│   ├── mysql_store.py         # MySQL 批量写入
│   └── neo4j_store.py         # Neo4j 图谱写入
│
├── models/                    # 数据建模
│   └── triples.py             # 三元组建模 + RDF 导出
│
├── data/                      # CSV 中间数据（按博物馆分目录）
│   ├── met/
│   ├── asianart/
│   └── philamuseum/
│
└── images/                    # 下载的文物图片（按博物馆分目录）
    ├── met/
    ├── asianart/
    └── philamuseum/
```

## 功能模块详解

### 一、数据爬取模块（scrapers/）

负责从 3 家海外博物馆网站爬取中国文物数据，输出统一格式的 CSV 文件和文物图片。

#### 1.1 爬虫基类 — `base.py`

提供所有博物馆爬虫的公共能力：

| 功能 | 说明 |
|------|------|
| HTTP 会话管理 | 基于 `requests.Session`，自动维护 Cookie 和连接池 |
| 重试机制 | 使用 `urllib3.Retry`，对 429/5xx 状态码自动重试 3 次，指数退避 |
| 请求限速 | 可配置的请求间隔（默认 0.5 秒），避免触发反爬 |
| 图片下载 | 将文物图片下载到本地 `images/` 目录，文件名与 object_id 对应 |
| 断点续爬 | 启动时加载已有的 CSV 文件，跳过已处理的 object_id |
| 批量保存 | 每爬取一定数量（200~500 条）自动写入 CSV，避免数据丢失 |
| 并发控制 | 通过 `ThreadPoolExecutor` 支持多线程并发爬取，可配置线程数 |

输出字段：`object_id`, `title_en`, `title_zh`, `time_period`, `dynasty`, `type`, `material`, `description`, `dimensions`, `detail_url`, `image_url`, `image_path`, `credit_line`, `accession_number`, `artist`, `country`

#### 1.2 大都会艺术博物馆爬虫 — `met_museum.py`

**API 接口：** Metropolitan Museum of Art Collection API（公开免费，无需认证）

**爬取流程：**

1. **搜索阶段** — 调用 `GET /search?departmentId=6&q=chinese&hasImages=true`，获取亚洲艺术部门中所有中国文物的 objectID 列表（约 9,700 个）
2. **详情获取** — 对每个 objectID 调用 `GET /objects/{id}`，获取完整的文物元数据
3. **后过滤** — 检查返回数据的 `culture`、`country`、`artistNationality` 字段，确保是中国文物
4. **图片下载** — 使用 `primaryImage` 字段的原图 URL 下载高清图片

**提取字段映射：**

| API 字段 | 系统字段 | 说明 |
|----------|----------|------|
| `objectID` | object_id | 博物馆唯一标识 |
| `title` | title_en | 文物英文名称 |
| `objectDate` | time_period | 年代描述（如 "6th-7th century"） |
| `dynasty` | dynasty | 朝代（如 "Qing Dynasty (1644-1911)"） |
| `classification` / `objectName` | type | 文物类型 |
| `medium` | material | 材质 |
| `dimensions` | dimensions | 尺寸 |
| `artistDisplayName` | artist | 艺术家姓名 |
| `creditLine` | credit_line | 来源说明 |
| `accessionNumber` | accession_number | 馆藏编号 |
| `primaryImage` | image_url | 原图 URL |
| `objectURL` | detail_url | 详情页链接 |
| `country` | country | 产地 |

**并发策略：** 使用 `ThreadPoolExecutor`（默认 5 线程），每提交 10 个请求后暂停 0.5 秒控制速率。

#### 1.3 费城艺术博物馆爬虫 — `philamuseum.py`

**API 接口：** Philadelphia Museum of Art 搜索 API + 详情 API

**爬取流程：**

1. **分页搜索** — 向 `POST https://prod.philamuseumsearch.org/v1/search` 发送请求，每次获取 48 条记录，通过 `paging.from` 翻页
2. **类型过滤** — 只保留 `type: "collections"` 的记录，过滤展览、研究等非藏品内容
3. **文化过滤** — 检查 `constituents` 和 `culture` 字段是否包含 "Chinese"
4. **详情补充** — 对每条记录调用 `GET https://pma-collection.web.app/gen2/v1/objects/{uuid}`，补充尺寸、地理等详情
5. **图片构造** — 从 `imageUrl`（Micrio 短 ID）构造 IIIF 图片 URL：`https://iiif.micr.io/{shortId}/full/max/0/default.jpg`

**提取字段映射：**

| API 字段 | 系统字段 | 说明 |
|----------|----------|------|
| `uuid` | object_id | 藏品唯一标识 |
| `title` | title_en | 文物名称 |
| `date` | time_period | 年代描述 |
| `dynasty` | dynasty | 朝代 |
| `category` | type | 分类（如 Paintings, Ceramics） |
| `medium` | material | 媒介/材质 |
| `summary` | description | 文物简介 |
| `artist` | artist | 艺术家 |
| `objectNumber` | accession_number | 馆藏编号 |
| `creditLine` | credit_line | 来源说明 |
| `Geography[0].Country` | country | 产地（从详情接口获取） |
| `Views.PrimaryView.micrio.shortId` | → image_url | 通过 IIIF 协议构造图片 URL |

#### 1.4 旧金山亚洲艺术博物馆爬虫 — `asian_art_museum.py`

该博物馆没有公开 API，提供两种数据获取方式：

**方式一：Selenium 自动爬取**

1. 使用 Chrome headless 模式访问 `collections.asianart.org`
2. 通过 URL 参数 `f[0]=field_place_of_origin:China` 筛选中国文物
3. 解析页面中的文物卡片，提取标题、图片、链接等
4. 对每个文物详情页，提取朝代、材质、尺寸等结构化字段
5. 自动翻页直到没有更多数据

**方式二：CSV 手动导入**

如果 Selenium 爬取失败（反爬保护），支持从预先准备好的 CSV 文件导入：

1. 将数据文件放置到 `data/asianart/asianart_import.csv`
2. 文件格式：UTF-8 编码，必须包含 `object_id` 和 `title_en` 列
3. 系统自动检测并导入，跳过已处理的记录

---

### 二、数据清洗模块（cleaners/）

负责对爬取的原始数据进行标准化处理，为后续翻译和存储做准备。

#### 2.1 清洗器 — `cleaner.py`

**核心功能：**

**（1）去重处理**
- 基于 `object_id` 字段进行去重，同一博物馆内同一文物只保留一条记录
- 跨博物馆不去重（同一文物可能被不同博物馆收藏）

**（2）朝代匹配**
- 内置 28 个中国标准朝代的中英文名称、起止年份
- 使用关键词优先匹配策略：先匹配具体朝代（如 "Northern Song"），再匹配大朝代（如 "Song"）
- 自动修正常见拼写错误（如 "northen" → "northern"）
- 匹配优先级：`Northern Song` > `Song`，`Western Han` > `Han`，避免误匹配

**标准朝代列表（部分）：**

| 英文名称 | 中文名称 | 起始年 | 结束年 |
|----------|----------|--------|--------|
| Shang Dynasty | 商朝 | -1600 | -1050 |
| Zhou Dynasty | 周朝 | -1100 | -256 |
| Han Dynasty | 汉朝 | -206 | 220 |
| Tang Dynasty | 唐朝 | 618 | 907 |
| Song Dynasty | 宋朝 | 960 | 1279 |
| Yuan Dynasty | 元朝 | 1271 | 1368 |
| Ming Dynasty | 明朝 | 1368 | 1644 |
| Qing Dynasty | 清朝 | 1644 | 1911 |

**（3）字段标准化**
- 统一空值表示：将 `nan`、`None`、`none` 统一替换为空字符串
- 去除首尾空白字符
- 过滤无效记录：必须有 `object_id` 和 `title_en`

**（4）艺术家提取**
- 从所有博物馆数据中提取不重复的艺术家列表
- 过滤掉 "Artist/maker unknown"、"Unknown" 等无效值
- 输出到 `data/clean_artists.csv`，供后续存储和图谱关联使用

**（5）朝代数据生成**
- 生成标准化的朝代数据 `data/clean_dynasties.csv`
- 包含 ID、中英文名称、起止年份，供 MySQL 和 Neo4j 导入使用

---

### 三、数据翻译模块（translators/）

负责将英文文物名称、描述等字段翻译为中文。

#### 3.1 翻译器 — `translator.py`

**双源翻译架构：**

```
翻译请求 → 检查缓存 → MyMemory API（免费）→ 百度翻译 API（付费）→ 返回结果
                ↓ 命中
            直接返回缓存
```

**（1）MyMemory 翻译（主源）**
- 接口：`GET https://api.mymemory.translated.net/get`
- 免费额度：每天 5,000 字符（提供邮箱可提高到 10,000）
- 单次限制：500 字符/请求
- 自动检测配额耗尽（返回 "MYMEMORY WARNING"），切换到备用源

**（2）百度翻译 API（备用源）**
- 接口：`GET https://fanyi-api.baidu.com/api/trans/vip/translate`
- 需要配置 `BAIDU_APP_ID` 和 `BAIDU_SECRET_KEY`
- 签名算法：`MD5(appid + q + salt + secret_key)`
- 翻译质量更高，适合专业术语

**（3）翻译缓存机制**
- 缓存文件：`data/translate_cache.json`
- 缓存键：`源语言|目标语言|原文前200字符`
- 命中缓存直接返回，不消耗 API 配额
- 每翻译 100 条自动保存一次缓存，异常退出不丢失

**（4）批量翻译**
- 支持对 DataFrame 的指定字段进行批量翻译
- 字段映射：`(title_en → title_zh)`
- 跳过已有翻译的记录，支持增量翻译

---

### 四、数据存储模块（storage/）

负责将清洗和翻译后的数据持久化到 MySQL 和 Neo4j。

#### 4.1 MySQL 存储 — `mysql_store.py`

**核心功能：**

**（1）批量写入**
- 使用 `executemany` 批量执行 INSERT，每批 500 条
- 自动提交/回滚事务，保证数据一致性

**（2）UPSERT 机制**
- 使用 `ON DUPLICATE KEY UPDATE` 实现存在则更新、不存在则插入
- 基于 `(museum_id, object_id)` 唯一索引判断重复
- 支持增量更新：重新运行不会产生重复数据

**（3）写入顺序**
由于外键依赖关系，数据按以下顺序写入：

```
museums → dynasties → artists → locations → artifacts → artifact_images → artifact_artist
```

**（4）字段类型处理**
- 自动将空字符串转为 NULL（避免外键约束报错）
- 安全整数转换（处理 `nan`、空值等异常输入）
- 日期字段使用 `date.today()` 自动填充

#### 4.2 Neo4j 图谱存储 — `neo4j_store.py`

**核心功能：**

**（1）约束创建**
为每种节点类型创建唯一性约束，避免重复节点：
```cypher
CREATE CONSTRAINT FOR (a:Artifact) REQUIRE a.object_id IS UNIQUE
CREATE CONSTRAINT FOR (m:Museum) REQUIRE m.name IS UNIQUE
CREATE CONSTRAINT FOR (d:Dynasty) REQUIRE d.name_en IS UNIQUE
CREATE CONSTRAINT FOR (ar:Artist) REQUIRE ar.name_en IS UNIQUE
```

**（2）节点与关系批量创建**

使用 Cypher 的 `UNWIND + MERGE` 进行批量操作（每批 200 条），一次写入同时创建节点和关系：

```cypher
UNWIND $batch AS item
MERGE (a:Artifact {object_id: item.object_id})
SET a.title_en = item.title_en, ...
WITH a, item
MATCH (m:Museum {name: item.museum})
MERGE (a)-[:STORED_IN]->(m)
WITH a, item
WHERE item.dynasty <> ''
MERGE (d:Dynasty {name_en: item.dynasty})
MERGE (a)-[:BELONGS_TO_DYNASTY]->(d)
...
```

**（3）朝代时间线**
- 为所有朝代创建节点，设置中英文名称和起止年份
- 根据年份衔接关系自动创建 `SUCCEEDED_BY` 后继关系（间隔 < 50 年）

**（4）艺术家关联**
- 创建艺术家节点（`Artist`）
- 建立 `(Artifact)-[:CREATED_BY]->(Artist)` 关系

**（5）图谱统计**
- 提供 `get_stats()` 方法，返回各类型节点和关系的数量统计

---

### 五、三元组建模模块（models/）

负责从结构化数据生成知识图谱三元组，并支持多种格式导出。

#### 5.1 三元组建模器 — `triples.py`

**（1）三元组生成**

从所有博物馆的文物数据中提取 `(主语, 谓语, 宾语)` 三元组：

| 主语 | 谓语 | 宾语 | 说明 |
|------|------|------|------|
| `artifact:{id}` | stored_in | `museum:{name}` | 文物藏于某博物馆 |
| `artifact:{id}` | belongs_to_dynasty | `dynasty:{name}` | 文物属于某朝代 |
| `artifact:{id}` | made_of | `material:{name}` | 文物材质 |
| `artifact:{id}` | classified_as | `type:{name}` | 文物类型 |
| `artifact:{id}` | created_by | `artist:{name}` | 文物创作者 |
| `artifact:{id}` | produced_in | `location:{name}` | 文物产地 |
| `dynasty:{name}` | start_year | `{year}` | 朝代起始年 |
| `dynasty:{name}` | end_year | `{year}` | 朝代结束年 |
| `dynasty:{name}` | name_zh | `{中文名}` | 朝代中文名 |

**（2）CSV 导出**
- 输出文件：`data/triples.csv`
- 格式：三列 CSV（subject, predicate, object）
- 可用于数据分析、导入其他图数据库

**（3）RDF/N-Triples 导出**
- 输出文件：`data/triples.nt`
- 格式：W3C N-Triples 标准格式
- 命名空间：`http://example.org/overseas-chinese-artifacts/`
- 可用于链接开放数据（LOD）发布、SPARQL 查询

示例输出：
```ntriples
<http://example.org/overseas-chinese-artifacts/artifact/30225> <http://example.org/overseas-chinese-artifacts/stored_in> <http://example.org/overseas-chinese-artifacts/museum/Metropolitan Museum of Art> .
<http://example.org/overseas-chinese-artifacts/artifact/30225> <http://example.org/overseas-chinese-artifacts/belongs_to_dynasty> <http://example.org/overseas-chinese-artifacts/dynasty/Qing Dynasty> .
```

---

### 六、配置模块（config.py）

统一管理系统配置，支持环境变量覆盖，方便 Docker 部署。

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| MySQL 连接 | `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | 127.0.0.1:3306 | 数据库连接参数 |
| Neo4j 连接 | `NEO4J_URI/USER/PASSWORD` | bolt://127.0.0.1:7687 | 图数据库连接参数 |
| 百度翻译 | `BAIDU_APP_ID/SECRET_KEY` | 空 | 百度翻译 API 凭据 |
| MyMemory | `MYMEMORY_EMAIL` | 空 | 可选，提高每日配额 |
| 爬虫线程数 | `CRAWL_WORKERS` | 5 | 并发线程数 |
| 请求间隔 | `CRAWL_DELAY` | 0.5s | 请求间隔秒数 |
| 请求超时 | `CRAWL_TIMEOUT` | 15s | 单次请求超时 |
| 重试次数 | `CRAWL_RETRIES` | 3 | 失败重试次数 |
| 图片下载 | `IMAGE_DOWNLOAD` | true | 是否下载图片 |
| 数据目录 | `DATA_DIR` | data | CSV 输出目录 |
| 图片目录 | `IMAGE_DIR` | images | 图片存储目录 |
| 日志级别 | `LOG_LEVEL` | INFO | 日志输出级别 |

---

### 七、主流程编排（main.py）

将所有模块串联为完整的数据处理流水线。

**流水线流程：**

```
step_crawl → step_clean → step_translate → step_store_mysql → step_store_neo4j → step_triples
    │             │              │                │                  │                │
    ▼             ▼              ▼                ▼                  ▼                ▼
 各博物馆CSV   清洗后CSV     翻译后CSV        MySQL数据库        Neo4j图数据库    三元组文件
```

**设计特点：**
- 每个步骤可独立运行，通过 `--step` 参数指定
- 中间结果以 CSV 文件持久化，任意步骤失败不影响已完成的步骤
- 统一日志输出，带时间戳和级别标识
- 支持 `--limit` 参数限制爬取数量，便于测试

## 数据格式

### CSV 中间文件

每个博物馆在 `data/<museum_key>/` 下生成以下文件：

| 文件 | 说明 |
|------|------|
| `<key>_raw.csv` | 爬取的原始数据 |
| `<key>_clean.csv` | 清洗后的数据 |
| `<key>_translated.csv` | 翻译后的数据 |

公共文件（`data/` 根目录）：

| 文件 | 说明 |
|------|------|
| `clean_dynasties.csv` | 朝代数据 |
| `clean_artists.csv` | 艺术家数据 |
| `triples.csv` | 三元组数据（CSV 格式） |
| `triples.nt` | 三元组数据（N-Triples / RDF 格式） |
| `translate_cache.json` | 翻译缓存 |

### 文物字段

| 字段 | 说明 | 示例 |
|------|------|------|
| object_id | 博物馆原始 ID | `30225` |
| title_en | 英文名称 | `Vase with Dragons and Clouds` |
| title_zh | 中文名称（翻译后） | `龙云纹瓷瓶` |
| time_period | 年代描述 | `18th century` |
| dynasty | 朝代 | `Qing Dynasty` |
| type | 文物类型 | `Ceramics` |
| material | 材质 | `Porcelain` |
| description | 介绍文本 | |
| dimensions | 尺寸 | `H. 14.6 cm` |
| detail_url | 详情页链接 | |
| image_url | 图片链接 | |
| credit_line | 来源说明 | |
| accession_number | 馆藏编号 | |

## 翻译说明

系统支持两种翻译源，自动切换：

| 翻译源 | 费用 | 配额 | 质量 |
|--------|------|------|------|
| MyMemory | 免费 | 5,000 字符/天 | 一般 |
| 百度翻译 | 付费 | 按套餐 | 较好 |

- 优先使用 MyMemory，配额耗尽后自动切换百度翻译
- 翻译结果缓存在 `data/translate_cache.json`，避免重复调用
- 百度翻译需要在环境变量中配置 `BAIDU_APP_ID` 和 `BAIDU_SECRET_KEY`

## 旧金山亚洲艺术博物馆数据获取

该博物馆没有公开 API，系统提供两种获取方式：

1. **Selenium 自动爬取**：使用 Chrome headless 浏览器访问网页（需要安装 Chrome）
2. **CSV 手动导入**：将预先准备好的数据文件放到 `data/asianart/asianart_import.csv`

导入 CSV 格式要求：UTF-8 编码，包含 `object_id` 和 `title_en` 字段。

## Neo4j 图谱查询示例

```cypher
-- 查看所有朝代的文物数量
MATCH (a:Artifact)-[:BELONGS_TO_DYNASTY]->(d:Dynasty)
RETURN d.name_zh AS dynasty, count(a) AS artifact_count
ORDER BY artifact_count DESC

-- 查看某件文物的完整关系
MATCH (a:Artifact {object_id: "30225"})-[r]->(n)
RETURN a, r, n

-- 查看某个朝代的所有文物
MATCH (a:Artifact)-[:BELONGS_TO_DYNASTY]->(d:Dynasty {name_en: "Qing Dynasty"})
RETURN a.title_en, a.title_zh, a.type
LIMIT 20

-- 查看艺术家及其创作的文物
MATCH (ar:Artist)<-[:CREATED_BY]-(a:Artifact)
RETURN ar.name_en AS artist, collect(a.title_en) AS works
LIMIT 10

-- 朝代时间线
MATCH (d1:Dynasty)-[:SUCCEEDED_BY]->(d2:Dynasty)
RETURN d1.name_zh AS from_dynasty, d2.name_zh AS to_dynasty
```

## MySQL 数据库表

系统共创建 35 张表，主要分为：

| 类别 | 表 | 说明 |
|------|-----|------|
| 核心数据 | museums, dynasties, artists, locations, artifacts, artifact_images | 文物及相关实体 |
| 关联表 | artifact_artist, artifact_location | 文物与实体的关联 |
| 用户系统 | users, roles, permissions, user_roles | 用户与权限 |
| 互动功能 | user_comments, user_favorites, artifact_likes, user_posts | 社区互动 |
| 内容审核 | audit_records, penalty_records, appeal_records | 审核与处罚 |
| 系统管理 | crawl_tasks, operation_logs, system_logs, security_logs | 运维日志 |

## 测试指南

### 第一步：验证服务启动

```bash
# 检查容器状态（mysql 和 neo4j 应为 healthy）
docker-compose ps
```

预期输出：

```
NAME           IMAGE                  STATUS
seitem-mysql   mysql:8.0              Up (healthy)
seitem-neo4j   neo4j:5.12-community   Up (healthy)
```

### 第二步：少量数据爬取测试

先用 `--limit` 参数爬取少量数据，验证爬虫是否正常工作：

```bash
# 仅爬取，每个博物馆限制 10 条
docker-compose run --rm app --step crawl --limit 10
```

检查爬取结果：

```bash
# 查看生成的 CSV 文件
ls -la data/met/
ls -la data/philamuseum/

# 查看 CSV 内容（前几行）
head -3 data/met/met_raw.csv
head -3 data/philamuseum/philamuseum_raw.csv

# 统计爬取数量
wc -l data/met/met_raw.csv data/philamuseum/philamuseum_raw.csv
```

### 第三步：数据清洗测试

```bash
# 清洗已爬取的数据
docker-compose run --rm app --step clean
```

验证清洗结果：

```bash
# 检查清洗后的文件
ls data/met/met_clean.csv data/philamuseum/philamuseum_clean.csv data/clean_dynasties.csv data/clean_artists.csv

# 查看朝代匹配情况（dynasty 列是否有值）
head -5 data/met/met_clean.csv | cut -d',' -f5
```

### 第四步：翻译测试

```bash
# 翻译文物名称
docker-compose run --rm app --step translate
```

验证翻译结果：

```bash
# 查看翻译后的文件
head -5 data/met/met_translated.csv

# 检查翻译缓存
cat data/translate_cache.json | python3 -m json.tool | head -20
```

### 第五步：数据库写入测试

```bash
# 写入 MySQL
docker-compose run --rm app --step mysql

# 写入 Neo4j
docker-compose run --rm app --step neo4j
```

验证 MySQL 数据：

```bash
# 进入 MySQL 容器查询
docker-compose exec mysql mysql -uroot -proot123 seitem -e "
  SELECT 'museums' AS category, COUNT(*) AS count FROM museums
  UNION ALL
  SELECT 'dynasties', COUNT(*) FROM dynasties
  UNION ALL
  SELECT 'artifacts', COUNT(*) FROM artifacts
  UNION ALL
  SELECT 'artists', COUNT(*) FROM artists;
"
```

验证 Neo4j 数据：

```bash
# 进入 Neo4j 容器查询
docker-compose exec neo4j cypher-shell -u neo4j -p neo4j123 \
  "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count ORDER BY count DESC;"
```

### 第六步：三元组生成测试

```bash
# 生成三元组
docker-compose run --rm app --step triples

# 查看 CSV 三元组
head -10 data/triples.csv

# 查看 RDF 三元组
head -5 data/triples.nt

# 统计三元组数量
wc -l data/triples.csv
```

### 第七步：全量爬取

少量测试通过后，执行全量爬取：

```bash
# 全流程（爬取 + 清洗 + 翻译 + 存储 + 三元组）
docker-compose run --rm app --step all

# 或分步执行（推荐，便于排查问题）
docker-compose run --rm app --step crawl
docker-compose run --rm app --step clean
docker-compose run --rm app --step translate
docker-compose run --rm app --step mysql
docker-compose run --rm app --step neo4j
docker-compose run --rm app --step triples
```

### 第八步：外部访问验证

如果需要从宿主机访问数据库（端口映射已在 docker-compose.yml 中注释，按需开启）：

**Neo4j Web 界面：**

1. 取消 `docker-compose.yml` 中 Neo4j 的 ports 注释，改为 `17474:7474` 和 `17687:7687`（避免与已有服务冲突）
2. `docker-compose up -d neo4j`
3. 浏览器访问 `http://localhost:17474`，用户 `neo4j`，密码 `neo4j123`

**MySQL 连接：**

```bash
# 通过 Docker 内部网络连接（无需端口映射）
docker-compose exec mysql mysql -uroot -proot123 seitem
```

### 测试检查清单

| 检查项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| 容器启动 | `docker-compose ps` | mysql、neo4j 状态为 healthy |
| 爬虫连通性 | `--step crawl --limit 1` | 有 CSV 输出，无报错 |
| 图片下载 | `ls images/met/` | 有 .jpg 文件 |
| 数据清洗 | `--step clean` | 生成 `*_clean.csv`，朝代列有匹配值 |
| 翻译功能 | `--step translate` | `*_translated.csv` 中 title_zh 列有中文 |
| MySQL 写入 | `--step mysql` | artifacts 表有数据 |
| Neo4j 写入 | `--step neo4j` | Artifact 节点存在 |
| 三元组生成 | `--step triples` | `triples.csv` 有数据行 |
| 断点续爬 | 再次运行 `--step crawl` | 跳过已爬取的 ID |
| 幂等写入 | 再次运行 `--step mysql` | 数据不重复 |
