from typing import Any, cast

from knowgraph.utils.environments import settings


class Neo4jWriter:
    """将节点和关系写入 Neo4j。"""

    LABELS = ["Artifact", "Museum", "Dynasty", "Material", "Artifact_type", "Location"]

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._driver = None
        self._nodes_written = 0
        self._rels_written = 0
        self._seen_nodes: set[tuple[str, str]] = set()
        self._seen_rels: set[tuple[str, str, str, str]] = set()

    @property
    def nodes_written(self) -> int:
        return self._nodes_written

    @property
    def rels_written(self) -> int:
        return self._rels_written

    def connect(self):
        if self.dry_run:
            return
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value()),
        )
        self._driver.verify_connectivity()

    def close(self):
        if self._driver:
            self._driver.close()

    # ---- 约束 ----

    def create_constraints(self):
        if self.dry_run:
            return
        assert self._driver is not None
        with self._driver.session() as session:
            for label in self.LABELS:
                constraint_name = f"unique_{label}_name"
                try:
                    session.run(
                        cast(Any, f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                             f"FOR (n:{label}) REQUIRE n.name IS UNIQUE")
                    )
                except Exception as e:
                    print(f"    警告: 无法为 {label} 创建约束: {e}")

    # ---- 清空 ----

    def clear_all(self):
        if self.dry_run:
            return
        assert self._driver is not None
        with self._driver.session() as session:
            for label in self.LABELS:
                try:
                    session.run(
                        cast(Any, f"DROP CONSTRAINT unique_{label}_name IF EXISTS")
                    )
                except Exception:
                    pass
            session.run("MATCH (n) DETACH DELETE n")

    # ---- 写入节点 ----

    def write_nodes(self, nodes: list[dict]) -> int:
        """批量写入节点（按标签分组，UNWIND + MERGE）。"""
        if self.dry_run:
            count = 0
            for n in nodes:
                key = (n["label"], n["name"])
                if key not in self._seen_nodes:
                    self._seen_nodes.add(key)
                    count += 1
            self._nodes_written += count
            return count

        assert self._driver is not None
        by_label: dict[str, list[dict]] = {}
        for n in nodes:
            label = n["label"]
            by_label.setdefault(label, []).append(n)

        written = 0
        with self._driver.session() as session:
            for label, batch in by_label.items():
                unique: list[dict] = []
                seen: set[str] = set()
                for n in batch:
                    name = n.get("name")
                    if not name or not str(name).strip():
                        continue
                    name = str(name).strip()
                    if name not in seen:
                        seen.add(name)
                        unique.append({
                            "entity_type": n.get("entity_type") or label.lower(),
                            "name": name,
                        })

                cypher = f"""
                    UNWIND $params AS p
                    MERGE (n:{label} {{name: p.name}})
                    SET n.entity_type = p.entity_type
                    RETURN count(n) AS cnt
                """
                result = session.run(cast(Any, cypher), params=unique)
                record = result.single()
                if record:
                    written += record["cnt"]

        self._nodes_written += written
        return written

    # ---- 写入关系 ----

    def write_relationships(self, rels: list[dict]) -> int:
        """批量写入关系（按类型分组，UNWIND + MERGE）。"""
        if self.dry_run:
            count = 0
            for r in rels:
                key = (r["s_label"], r["s_name"], r["predicate"], r["o_name"])
                if key not in self._seen_rels:
                    self._seen_rels.add(key)
                    count += 1
            self._rels_written += count
            return count

        assert self._driver is not None
        by_type: dict[str, list[dict]] = {}
        for r in rels:
            rel_type = r["predicate"]
            by_type.setdefault(rel_type, []).append(r)

        written = 0
        with self._driver.session() as session:
            for rel_type, batch in by_type.items():
                unique: list[dict] = []
                seen: set[tuple[str, str, str, str]] = set()
                for r in batch:
                    key = (r["s_label"], r["s_name"], r["o_label"], r["o_name"])
                    if key not in seen:
                        seen.add(key)
                        unique.append(r)

                params = [
                    {
                        "s_label": r["s_label"],
                        "s_name": r["s_name"],
                        "o_label": r["o_label"],
                        "o_name": r["o_name"],
                    }
                    for r in unique
                ]

                s_label = self._escape_label(batch[0]["s_label"])
                o_label = self._escape_label(batch[0]["o_label"])
                cypher = f"""
                    UNWIND $params AS p
                    MATCH (s:{s_label} {{name: p.s_name}})
                    MATCH (o:{o_label} {{name: p.o_name}})
                    MERGE (s)-[:{rel_type}]->(o)
                    RETURN count(*) AS cnt
                """
                result = session.run(cast(Any, cypher), params=params)
                record = result.single()
                if record:
                    written += record["cnt"]

        self._rels_written += written
        return written

    @staticmethod
    def _escape_label(label: str) -> str:
        return "".join(c for c in label if c.isalnum() or c == "_")
