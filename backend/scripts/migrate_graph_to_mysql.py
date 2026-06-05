#!/usr/bin/env python3

import argparse
import re
import sys
from datetime import datetime
from typing import Any

import psycopg
import pymysql
import pymysql.cursors

# ============================================================================
# 数据库连接配置
# ============================================================================

PG_CONFIG = {
    "host": "",
    "port": 10004,
    "database": "",
    "user": "",
    "password": "",
}

MYSQL_CONFIG = {
    "host": "",
    "port": ,
    "database": "",
    "user": "",
    "password": "",
    "charset": "utf8mb4",
}

GRAPH_NAME = "graph"

DEFAULT_LIMIT = 20

# ============================================================================
# 工具函数
# ============================================================================


def safe_str(value: Any, max_len: int | None = None) -> str | None:
    """安全转换为字符串，None / 空串 → None。可选截断。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


def truncate(value: str | None, max_len: int) -> str:
    """截断字符串到指定长度，用于 NOT NULL 字段 fallback。"""
    if not value:
        return ""
    return value[:max_len] if len(value) > max_len else value


def parse_location(location_text: str | None) -> tuple[str | None, str | None]:
    """解析 location 字段为 (city, country)。"""
    if not location_text or not location_text.strip():
        return None, None
    text = location_text.strip()
    parts = [p.strip() for p in text.split(",")]
    if len(parts) == 1:
        return None, parts[0]
    elif len(parts) >= 2:
        return parts[0], parts[-1]
    return None, None


def extract_first_part(text: str | None, sep: str = ";") -> str | None:
    """提取分隔符前的第一部分，去重去噪。"""
    if not text or not text.strip():
        return None
    parts = [p.strip() for p in text.split(sep) if p.strip()]
    # 去重
    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    return unique[0] if unique else None


# ============================================================================
# 图数据库 Cypher 查询
# ============================================================================


class GraphQuery:
    """封装 Cypher 查询（Apache AGE 格式）。"""

    def __init__(self, pg_conn):
        self.conn = pg_conn
        self.graph = GRAPH_NAME

    def _execute_cypher(
        self,
        cypher: str,
        columns: list[str],
        params: dict | None = None,
    ) -> list[dict[str, Any]]:
        """执行 Cypher 查询，返回字典列表。"""
        col_defs = ", ".join(f"{c} agtype" for c in columns)
        # 处理参数占位符
        if params:
            for key, val in params.items():
                placeholder = f"${key}"
                if placeholder in cypher:
                    if isinstance(val, str):
                        # Cypher 使用 \' 转义单引号（而非 SQL 的 ''）
                        escaped = val.replace("\\", "\\\\").replace("'", "\\'")
                        cypher = cypher.replace(placeholder, f"'{escaped}'")
                    elif isinstance(val, (int, float)):
                        cypher = cypher.replace(placeholder, str(val))
                    elif val is None:
                        cypher = cypher.replace(placeholder, "NULL")
                    elif isinstance(val, bool):
                        cypher = cypher.replace(placeholder, "true" if val else "false")

        sql = f"SELECT * FROM cypher('{self.graph}', $$ {cypher} $$) AS ({col_defs})"
        with self.conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            if not rows:
                return []
            # 解析 agtype (JSON) 值
            import json

            results: list[dict[str, Any]] = []
            for row in rows:
                record: dict[str, Any] = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, str):
                        try:
                            record[col] = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            record[col] = val
                    else:
                        record[col] = val
                results.append(record)
            return results

    # ---- 节点查询 ----

    def get_all_museums(self) -> list[dict]:
        """查询所有博物馆节点。"""
        cypher = """
            MATCH (m:Museum)
            RETURN m.name AS name, m.description AS description
        """
        return self._execute_cypher(cypher, ["name", "description"])

    def get_all_dynasties(self) -> list[dict]:
        """查询所有朝代节点。"""
        cypher = """
            MATCH (d:Dynasty)
            RETURN d.name AS name, d.description AS description
        """
        return self._execute_cypher(cypher, ["name", "description"])

    def get_all_locations(self) -> list[dict]:
        """查询所有地点节点。"""
        cypher = """
            MATCH (l:Location)
            RETURN l.name AS name
        """
        return self._execute_cypher(cypher, ["name"])

    def get_all_artifact_types(self) -> list[dict]:
        """查询所有文物类型节点。"""
        cypher = """
            MATCH (t:Artifact_type)
            RETURN t.name AS name
        """
        return self._execute_cypher(cypher, ["name"])

    def get_all_materials(self) -> list[dict]:
        """查询所有材质节点。"""
        cypher = """
            MATCH (m:Material)
            RETURN m.name AS name
        """
        return self._execute_cypher(cypher, ["name"])

    def get_artifacts_with_relations(self, limit: int = 0) -> list[dict]:
        """查询文物节点及其所有关系（聚合）。"""
        # 先获取文物列表（可能带限制）
        if limit > 0:
            cypher = """
                MATCH (a:Artifact)
                RETURN a.name AS name, a.raw_name AS raw_name
                LIMIT $limit
            """
        else:
            cypher = """
                MATCH (a:Artifact)
                RETURN a.name AS name, a.raw_name AS raw_name
            """
        rows = self._execute_cypher(cypher, ["name", "raw_name"], params={"limit": limit} if limit > 0 else None)

        # 为每个文物获取关系
        for row in rows:
            artifact_name = row["name"]

            # 获取博物馆 (collected_by)
            museum_rows = self._execute_cypher(
                """
                MATCH (a:Artifact {name: $name})-[r:collected_by]->(m:Museum)
                RETURN m.name AS name
                """,
                ["name"],
                params={"name": artifact_name},
            )
            row["museums"] = [m["name"] for m in museum_rows]

            # 获取朝代 (belongs_to_dynasty)
            dynasty_rows = self._execute_cypher(
                """
                MATCH (a:Artifact {name: $name})-[r:belongs_to_dynasty]->(d:Dynasty)
                RETURN d.name AS name
                """,
                ["name"],
                params={"name": artifact_name},
            )
            row["dynasties"] = [d["name"] for d in dynasty_rows]

            # 获取类型 (is_type_of)
            type_rows = self._execute_cypher(
                """
                MATCH (a:Artifact {name: $name})-[r:is_type_of]->(t:Artifact_type)
                RETURN t.name AS name
                """,
                ["name"],
                params={"name": artifact_name},
            )
            row["artifact_types"] = [t["name"] for t in type_rows]

            # 获取材质 (made_of_material)
            material_rows = self._execute_cypher(
                """
                MATCH (a:Artifact {name: $name})-[r:made_of_material]->(m:Material)
                RETURN m.name AS name
                """,
                ["name"],
                params={"name": artifact_name},
            )
            row["materials"] = [m["name"] for m in material_rows]

        return rows

    def get_museum_locations(self) -> list[dict]:
        """查询博物馆所在地关系。"""
        cypher = """
            MATCH (m:Museum)-[r:located_at]->(l:Location)
            RETURN m.name AS museum_name, l.name AS location_name
        """
        return self._execute_cypher(cypher, ["museum_name", "location_name"])


# ============================================================================
# PostgreSQL artifact_raw 查询
# ============================================================================


class PGRawQuery:
    """查询 artifact_raw 表获取文物详细信息。"""

    def __init__(self, pg_conn):
        self.conn = pg_conn

    def get_artifact_by_title(self, title: str) -> dict | None:
        """根据标题查询 artifact_raw 记录。"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT object_id, title, period, type, material, description,
                       dimensions, museum, location, detail_url, image_url,
                       credit_line, accession_number, artist, crawl_date
                FROM artifact_raw
                WHERE title = %s
                LIMIT 1
                """,
                (title,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [
                "object_id", "title", "period", "type", "material", "description",
                "dimensions", "museum", "location", "detail_url", "image_url",
                "credit_line", "accession_number", "artist", "crawl_date",
            ]
            return dict(zip(cols, row, strict=False))

    def get_artifacts_by_titles(self, titles: list[str]) -> dict[str, dict]:
        """批量根据标题查询 artifact_raw 记录。"""
        if not titles:
            return {}
        with self.conn.cursor() as cur:
            # 使用 ANY 批量查询
            cur.execute(
                """
                SELECT object_id, title, period, type, material, description,
                       dimensions, museum, location, detail_url, image_url,
                       credit_line, accession_number, artist, crawl_date
                FROM artifact_raw
                WHERE title = ANY(%s)
                """,
                (titles,),
            )
            cols = [
                "object_id", "title", "period", "type", "material", "description",
                "dimensions", "museum", "location", "detail_url", "image_url",
                "credit_line", "accession_number", "artist", "crawl_date",
            ]
            result: dict[str, dict] = {}
            for row in cur.fetchall():
                record = dict(zip(cols, row, strict=False))
                result[record["title"]] = record
            return result


# ============================================================================
# MySQL 操作
# ============================================================================


class MySQLStore:
    """MySQL 数据库操作封装。"""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql: str, params: tuple | None = None) -> int:
        """执行 SQL，返回 lastrowid（若无则返回 rowcount）。"""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid or cur.rowcount

    def insert(self, table: str, data: dict) -> int:
        """插入一条记录，返回 lastrowid（若无自增主键则返回 rowcount）。"""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def query_one(self, sql: str, params: tuple | None = None) -> dict | None:
        """查询单条记录，返回字典。"""
        with self.conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def query_all(self, sql: str, params: tuple | None = None) -> list[dict]:
        """查询多条记录，返回字典列表。"""
        with self.conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def get_museum_id(self, name: str) -> int | None:
        """根据博物馆英文名查询 ID。"""
        row = self.query_one("SELECT id FROM museums WHERE name = %s", (name,))
        return row["id"] if row else None

    def get_dynasty_id(self, name_en: str) -> int | None:
        """根据朝代英文名查询 ID。"""
        row = self.query_one("SELECT id FROM dynasties WHERE name_en = %s", (name_en,))
        return row["id"] if row else None

    def truncate_all(self):
        """清空所有表数据（用于测试）。"""
        tables = ["artifact_artist", "artifact_images", "artifacts", "artists", "dynasties", "museums"]
        with self.conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for t in tables:
                cur.execute(f"TRUNCATE TABLE {t}")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        self.conn.commit()
        print("  已清空所有表数据")


# ============================================================================
# 迁移器
# ============================================================================


class GraphToMySQLMigrator:
    """图数据库 → MySQL 迁移器。"""

    def __init__(
        self,
        dry_run: bool = False,
        limit: int = 0,
        clean: bool = False,
    ):
        self.dry_run = dry_run
        self.limit = limit if limit > 0 else DEFAULT_LIMIT
        self.clean = clean

        self.pg_conn = None
        self.mysql_conn = None
        self.graph: GraphQuery | None = None
        self.pg_raw: PGRawQuery | None = None
        self.mysql: MySQLStore | None = None

    def connect(self):
        """建立数据库连接。"""
        print("=" * 60)
        print("图数据库 (Apache AGE) → MySQL 数据迁移")
        print("=" * 60)
        print(f"  试运行: {'是' if self.dry_run else '否'}")
        print(f"  限制:   {self.limit} 条")
        print(f"  清空旧数据: {'是' if self.clean else '否'}")
        print()

        print(f"[PG] 连接 PostgreSQL: {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}")
        self.pg_conn = psycopg.connect(
            host=PG_CONFIG["host"],
            port=PG_CONFIG["port"],
            dbname=PG_CONFIG["database"],
            user=PG_CONFIG["user"],
            password=PG_CONFIG["password"],
        )
        self.pg_conn.autocommit = True
        print("[PG] 连接成功")

        self.graph = GraphQuery(self.pg_conn)
        self.pg_raw = PGRawQuery(self.pg_conn)

        if not self.dry_run:
            print(f"[MySQL] 连接 Docker MySQL: {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")
            self.mysql_conn = pymysql.connect(**MYSQL_CONFIG)
            self.mysql = MySQLStore(self.mysql_conn)
            print("[MySQL] 连接成功")

    def close(self):
        """关闭数据库连接。"""
        if self.pg_conn:
            self.pg_conn.close()
        if self.mysql_conn:
            self.mysql_conn.close()
        print("\n连接已关闭")

    # ---- Step 1: museums ----

    def migrate_museums(self) -> int:
        print("\n[Step 1/6] 迁移 museums（博物馆）...")

        museums = self.graph.get_all_museums()
        print(f"  从图数据库获取到 {len(museums)} 个博物馆节点")

        for m in museums[:5]:
            print(f"    - {m['name']}")
        if len(museums) > 5:
            print(f"    ... 共 {len(museums)} 个")

        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(museums)} 条 museums 记录")
            return len(museums)

        # 先查询已存在的博物馆，避免重复插入
        existing = {r["name"] for r in self.mysql.query_all("SELECT name FROM museums")}

        inserted = 0
        for m in museums:
            name = m["name"].strip()
            if name in existing:
                continue

            data = {
                "name": name,
                "short_name": None,
                "country": "Unknown",
                "city": None,
                "website": None,
                "collection_url": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "latitude": None,
                "longitude": None,
            }
            last_id = self.mysql.insert("museums", data)
            if last_id:
                existing.add(name)
                inserted += 1

        print(f"  已插入 {inserted} 条 museums 记录")
        return inserted

    # ---- Step 2: dynasties ----

    def migrate_dynasties(self) -> int:
        print("\n[Step 2/6] 迁移 dynasties（朝代）...")

        dynasties = self.graph.get_all_dynasties()
        print(f"  从图数据库获取到 {len(dynasties)} 个朝代节点")

        # 去重
        seen: set[str] = set()
        unique_dynasties: list[dict] = []
        for d in dynasties:
            name = d["name"].strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                unique_dynasties.append({"name": name, "description": d.get("description")})

        print(f"  去重后 {len(unique_dynasties)} 个朝代")
        for d in unique_dynasties[:5]:
            print(f"    - {d['name']}")

        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(unique_dynasties)} 条 dynasties 记录")
            return len(unique_dynasties)

        existing = {r["name_en"]: r["id"] for r in self.mysql.query_all("SELECT id, name_en FROM dynasties")}

        inserted = 0
        for d in unique_dynasties:
            name_en = d["name"][:100]
            if name_en in existing:
                continue

            data = {
                "name_zh": truncate(name_en, 50),  # name_zh NOT NULL，用英文名填充
                "name_en": name_en,
                "start_year": None,
                "end_year": None,
                "description": safe_str(d.get("description")),
                "created_at": datetime.now(),
            }
            last_id = self.mysql.insert("dynasties", data)
            if last_id:
                existing[name_en] = last_id
                inserted += 1

        print(f"  已插入 {inserted} 条 dynasties 记录")
        return inserted

    # ---- Step 3: artists ----

    @staticmethod
    def parse_artists(artist_text: str | None) -> list[str]:
        """拆分 artist 字段，处理多艺术家情况。"""
        if not artist_text or not artist_text.strip():
            return []
        text = artist_text.strip()
        # 排除的非艺术家关键词
        skip_words = {
            "unknown", "anonymous", "various", "n/a",
            "artist/maker unknown", "artist", "maker unknown",
            "unknown artist", "unknown maker",
        }
        # 按多种分隔符拆分
        for sep in ["; ", ";", ", ", ",", "/ ", "/"]:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                return [
                    p for p in parts
                    if len(p) > 1 and p.lower() not in skip_words
                ]
        if text.lower() not in skip_words:
            return [text]
        return []

    def migrate_artists(self) -> int:
        print("\n[Step 3/6] 迁移 artists（艺术家）...")

        pg_artist_map = getattr(self, "_pg_artist_map", {})

        if not pg_artist_map:
            print("  无艺术家数据，跳过")
            return 0

        # 收集所有艺术家名字
        all_names: set[str] = set()
        for names in pg_artist_map.values():
            all_names.update(names)

        print(f"  从 artifact_raw.artist 提取到 {len(all_names)} 个独立艺术家")

        if self.dry_run:
            for name in sorted(all_names)[:5]:
                print(f"    - {name}")
            print(f"  [DRY RUN] 将插入 {len(all_names)} 条 artists 记录")
            return len(all_names)

        # 检查已存在的艺术家
        existing = {r["name_en"]: r["id"] for r in self.mysql.query_all("SELECT id, name_en FROM artists")}

        inserted = 0
        self._artist_map: dict[str, int] = {}  # name_en → mysql_id
        for name in sorted(all_names):
            if name in existing:
                self._artist_map[name] = existing[name]
                continue

            data = {
                "name_zh": None,  # 图数据库无中文名
                "name_en": truncate(name, 200),
                "birth_year": None,
                "death_year": None,
                "dynasty_id": None,
                "biography": None,
                "baidu_url": None,
                "wiki_url": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            last_id = self.mysql.insert("artists", data)
            if last_id:
                self._artist_map[name] = last_id
                existing[name] = last_id
                inserted += 1

        print(f"  已插入 {inserted} 条 artists 记录（共 {len(self._artist_map)} 个）")
        return inserted

    # ---- Step 4: artifacts ----

    def migrate_artifacts(self) -> int:
        print(f"\n[Step 4/6] 迁移 artifacts（文物主表）... (限制 {self.limit} 条)")

        # 1. 从图数据库获取文物节点及其关系
        graph_artifacts = self.graph.get_artifacts_with_relations(limit=self.limit)
        print(f"  从图数据库获取到 {len(graph_artifacts)} 个文物节点")

        # 2. 从 artifact_raw 获取详细信息
        titles = [a["name"] for a in graph_artifacts]
        pg_details = self.pg_raw.get_artifacts_by_titles(titles)
        print(f"  从 artifact_raw 匹配到 {len(pg_details)} 条详细记录")

        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(graph_artifacts)} 条 artifacts 记录")
            for i, a in enumerate(graph_artifacts[:5]):
                pg = pg_details.get(a["name"], {})
                print(f"    {i+1}. title_en={a['name']}")
                print(f"       museum={a.get('museums', [])}, dynasty={a.get('dynasties', [])}")
                print(f"       type={a.get('artifact_types', [])}, materials={a.get('materials', [])[:3]}...")
                print(f"       pg: period={pg.get('period')}, detail_url={pg.get('detail_url')}")
            return len(graph_artifacts)

        inserted = 0
        self._pg_artist_map: dict[int, list[str]] = {}  # artifact_mysql_id → [artist_names]
        for a in graph_artifacts:
            artifact_name = a["name"]
            pg = pg_details.get(artifact_name, {})

            # museum_id: 从 MySQL museums 表查询（用英文名）
            museum_name = a["museums"][0] if a["museums"] else (pg.get("museum") or "").strip()
            museum_id = self.mysql.get_museum_id(museum_name) if museum_name else None
            # museum_id 是 NOT NULL，如果找不到则使用第一个博物馆作为默认值
            if museum_id is None:
                first_museum = self.mysql.query_one("SELECT id FROM museums ORDER BY id LIMIT 1")
                museum_id = first_museum["id"] if first_museum else None

            # dynasty_id: 从 MySQL dynasties 表查询（用英文名 name_en）
            dynasty_name = a["dynasties"][0] if a["dynasties"] else None
            dynasty_id = None
            if dynasty_name:
                dynasty_id = self.mysql.get_dynasty_id(dynasty_name)

            # type: 从 is_type_of 关系获取
            artifact_type = a["artifact_types"][0] if a["artifact_types"] else safe_str(pg.get("type"))

            # material: 聚合 made_of_material 关系
            materials = a.get("materials", [])
            material_str = "; ".join(materials) if materials else safe_str(pg.get("material"))

            # 从 artifact_raw 获取的额外字段
            object_id = safe_str(pg.get("object_id")) or ""
            period = safe_str(pg.get("period"))
            description = safe_str(pg.get("description"))
            dimensions = safe_str(pg.get("dimensions"))
            detail_url = safe_str(pg.get("detail_url"))
            image_url = safe_str(pg.get("image_url"))
            credit_line = safe_str(pg.get("credit_line"))
            accession_number = safe_str(pg.get("accession_number"))
            crawl_date = pg.get("crawl_date")

            data = {
                "object_id": truncate(object_id, 100),
                "title_zh": None,  # 图数据库无中文名
                "title_en": truncate(artifact_name, 500),
                "time_period": truncate(period, 200),
                "dynasty_id": dynasty_id,
                "type": truncate(artifact_type, 100),
                "material": truncate(material_str, 200),
                "description": description,
                "dimensions": truncate(dimensions, 200),
                "museum_id": museum_id,
                "location_id": None,
                "detail_url": truncate(detail_url, 500),
                "image_url": truncate(image_url, 500),
                "image_path": None,
                "credit_line": truncate(credit_line, 300),
                "accession_number": truncate(accession_number, 100),
                "crawl_date": crawl_date,
                "image_validated": None,
                "last_updated": datetime.now(),
                "created_at": datetime.now(),
                "provenance": None,
                "current_status": None,
            }
            last_id = self.mysql.insert("artifacts", data)
            if last_id:
                inserted += 1
                # 收集该文物的艺术家名字，供 artifact_artist 步骤使用
                artist_names = self.parse_artists(safe_str(pg.get("artist")))
                if artist_names:
                    self._pg_artist_map[last_id] = artist_names

        print(f"  已插入 {inserted} 条 artifacts 记录")
        return inserted

    # ---- Step 5: artifact_images ----

    def migrate_artifact_images(self) -> int:
        print("\n[Step 5/6] 迁移 artifact_images（文物图片）...")

        # 查询 MySQL 中有 image_url 的 artifacts
        if self.dry_run:
            print(f"  [DRY RUN] 将插入对应数量的 artifact_images 记录")
            return 0

        rows = self.mysql.query_all(
            "SELECT id, image_url FROM artifacts WHERE image_url IS NOT NULL AND image_url != ''"
        )
        print(f"  找到 {len(rows)} 条有图片的 artifacts 记录")

        inserted = 0
        for row in rows:
            data = {
                "artifact_id": row["id"],
                "image_url": row["image_url"],
                "image_path": None,
                "is_primary": 1,
                "sort_order": 1,
            }
            last_id = self.mysql.insert("artifact_images", data)
            if last_id:
                inserted += 1

        print(f"  已插入 {inserted} 条 artifact_images 记录")
        return inserted

    # ---- Step 6: artifact_artist ----

    def migrate_artifact_artist(self) -> int:
        print("\n[Step 6/6] 迁移 artifact_artist（文物-艺术家关联）...")

        pg_artist_map = getattr(self, "_pg_artist_map", {})
        artist_map = getattr(self, "_artist_map", {})

        if not pg_artist_map:
            print("  无文物-艺术家关联数据，跳过")
            return 0

        print(f"  共 {len(pg_artist_map)} 个文物有艺术家信息")

        if self.dry_run:
            for artifact_id, names in list(pg_artist_map.items())[:5]:
                print(f"    artifact_id={artifact_id}: {names}")
            total = sum(len(names) for names in pg_artist_map.values())
            print(f"  [DRY RUN] 将插入 {total} 条 artifact_artist 记录")
            return total

        inserted = 0
        skipped = 0
        for artifact_id, names in pg_artist_map.items():
            for name in names:
                artist_id = artist_map.get(name)
                if artist_id is None:
                    skipped += 1
                    continue
                data = {
                    "artifact_id": artifact_id,
                    "artist_id": artist_id,
                    "relationship_type": "created_by",
                }
                # artifact_artist 表无自增主键，用 rowcount 判断
                rowcount = self.mysql.insert("artifact_artist", data)
                if rowcount:
                    inserted += 1

        print(f"  已插入 {inserted} 条 artifact_artist 关联 (跳过 {skipped} 因 artist 未找到)")
        return inserted

    # ---- 主流程 ----

    def run(self):
        start = datetime.now()

        self.connect()
        try:
            if self.clean and not self.dry_run:
                self.mysql.truncate_all()

            self.migrate_museums()
            self.migrate_dynasties()
            # artifacts 必须先于 artists 执行，因为需要从 artifact_raw.artist 提取艺术家名字
            self.migrate_artifacts()
            self.migrate_artists()
            self.migrate_artifact_images()
            self.migrate_artifact_artist()
        except Exception as e:
            print(f"\n错误: {e}")
            import traceback

            traceback.print_exc()
            return 1
        finally:
            self.close()

        elapsed = (datetime.now() - start).total_seconds()
        print("\n" + "=" * 60)
        print("迁移完成")
        print("=" * 60)
        print(f"  总耗时: {elapsed:.1f} 秒")

        if self.dry_run:
            print("\n提示: 这是试运行结果。去掉 --dry-run 参数进行实际迁移。")
        else:
            print(f"\n迁移已完成到 Docker MySQL (localhost:{MYSQL_CONFIG['port']})")
            print(f"可以用 DataGrip 连接查看数据:")
            print(f"  Host: {MYSQL_CONFIG['host']}")
            print(f"  Port: {MYSQL_CONFIG['port']}")
            print(f"  Database: {MYSQL_CONFIG['database']}")
            print(f"  User: {MYSQL_CONFIG['user']}")
            print(f"  Password: {MYSQL_CONFIG['password']}")

        return 0


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="图数据库 (Apache AGE) → Docker MySQL 数据迁移",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 试运行（验证映射逻辑）
  python backend/scripts/migrate_graph_to_mysql.py --dry-run

  # 限制 20 条测试迁移
  python backend/scripts/migrate_graph_to_mysql.py --limit 20

  # 清空旧数据后迁移 20 条
  python backend/scripts/migrate_graph_to_mysql.py --limit 20 --clean

  # 迁移 100 条
  python backend/scripts/migrate_graph_to_mysql.py --limit 100
        """,
    )
    parser.add_argument("--dry-run", action="store_true", help="试运行，不写入 MySQL")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"限制迁移文物条数 (默认: {DEFAULT_LIMIT})")
    parser.add_argument("--clean", action="store_true", help="迁移前清空 MySQL 所有表数据")
    args = parser.parse_args()

    migrator = GraphToMySQLMigrator(
        dry_run=args.dry_run,
        limit=args.limit,
        clean=args.clean,
    )
    return migrator.run()


if __name__ == "__main__":
    sys.exit(main())
