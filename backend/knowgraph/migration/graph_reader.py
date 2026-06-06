"""Apache AGE 图数据库 Cypher 查询读取器。"""

import json
from typing import Any

import psycopg

from knowgraph.utils.environments import settings


class AGEGraphReader:
    """从 Apache AGE 读取节点和关系。"""

    def __init__(self, conn: "psycopg.Connection | None" = None):
        self._own_conn = conn is None
        self.conn = conn
        self.graph = settings.AGE_GRAPH_NAME

    def connect(self):
        if self.conn is not None:
            return
        self.conn = psycopg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD.get_secret_value(),
        )
        self.conn.autocommit = True

    def close(self):
        if self._own_conn and self.conn:
            self.conn.close()

    def _execute(self, cypher: str, columns: list[str], params: dict | None = None) -> list[dict[str, Any]]:
        """执行 Cypher 查询，返回字典列表。"""
        col_defs = ", ".join(f"{c} agtype" for c in columns)
        if params:
            for key, val in params.items():
                placeholder = f"${key}"
                if placeholder in cypher:
                    if isinstance(val, str):
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

    # ---- 计数 ----

    def count_nodes(self) -> int:
        rows = self._execute("MATCH (v) RETURN count(v) AS cnt", ["cnt"])
        return int(rows[0]["cnt"]) if rows else 0

    def count_rels(self) -> int:
        rows = self._execute("MATCH ()-[r]->() RETURN count(r) AS cnt", ["cnt"])
        return int(rows[0]["cnt"]) if rows else 0

    # ---- 节点查询 ----

    def get_all_museums(self) -> list[dict]:
        return self._execute(
            "MATCH (m:Museum) RETURN m.name AS name, m.description AS description",
            ["name", "description"],
        )

    def get_all_dynasties(self) -> list[dict]:
        return self._execute(
            "MATCH (d:Dynasty) RETURN d.name AS name, d.description AS description",
            ["name", "description"],
        )

    def get_all_locations(self) -> list[dict]:
        return self._execute("MATCH (l:Location) RETURN l.name AS name", ["name"])

    def get_all_artifact_types(self) -> list[dict]:
        return self._execute("MATCH (t:Artifact_type) RETURN t.name AS name", ["name"])

    def get_all_materials(self) -> list[dict]:
        return self._execute("MATCH (m:Material) RETURN m.name AS name", ["name"])

    def get_all_nodes(self) -> list[dict]:
        """获取所有节点（标签 + 属性）。"""
        return self._execute(
            """
            MATCH (v) RETURN labels(v) AS labels, v.entity_type AS entity_type,
            v.name AS name, id(v) AS age_id
            """,
            ["labels", "entity_type", "name", "age_id"],
        )

    # ---- 文物 + 关系查询 ----

    def get_artifacts_with_relations(self, limit: int = 0) -> list[dict]:
        """查询文物节点及其所有关系（聚合）。"""
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
        rows = self._execute(
            cypher, ["name", "raw_name"],
            params={"limit": limit} if limit > 0 else None,
        )

        for row in rows:
            artifact_name = row["name"]
            row["museums"] = [m["name"] for m in self._execute(
                "MATCH (a:Artifact {name: $name})-[r:collected_by]->(m:Museum) RETURN m.name AS name",
                ["name"], params={"name": artifact_name},
            )]
            row["dynasties"] = [d["name"] for d in self._execute(
                "MATCH (a:Artifact {name: $name})-[r:belongs_to_dynasty]->(d:Dynasty) RETURN d.name AS name",
                ["name"], params={"name": artifact_name},
            )]
            row["artifact_types"] = [t["name"] for t in self._execute(
                "MATCH (a:Artifact {name: $name})-[r:is_type_of]->(t:Artifact_type) RETURN t.name AS name",
                ["name"], params={"name": artifact_name},
            )]
            row["materials"] = [m["name"] for m in self._execute(
                "MATCH (a:Artifact {name: $name})-[r:made_of_material]->(m:Material) RETURN m.name AS name",
                ["name"], params={"name": artifact_name},
            )]
        return rows

    def get_all_relationships(self) -> list[dict]:
        """获取所有关系（三元组）。"""
        return self._execute(
            """
            MATCH (s)-[r]->(o)
            RETURN labels(s) AS s_labels, s.entity_type AS s_type, s.name AS s_name,
                   type(r) AS predicate,
                   labels(o) AS o_labels, o.entity_type AS o_type, o.name AS o_name
            """,
            ["s_labels", "s_type", "s_name", "predicate", "o_labels", "o_type", "o_name"],
        )

    def get_museum_locations(self) -> list[dict]:
        return self._execute(
            "MATCH (m:Museum)-[r:located_at]->(l:Location) RETURN m.name AS museum_name, l.name AS location_name",
            ["museum_name", "location_name"],
        )

    # ---- artifact_raw 表查询 ----

    def get_artifact_details_by_titles(self, titles: list[str]) -> dict[str, dict]:
        """批量根据标题查询 artifact_raw 记录。"""
        if not titles:
            return {}
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT object_id, title, period, type, material, description,
                       dimensions, museum, location, detail_url, image_url,
                       credit_line, accession_number, artist, crawl_date
                FROM artifact_raw WHERE title = ANY(%s)
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
