"""
Neo4j知识图谱存储模块
负责将文物数据建模为三元组并存入Neo4j图数据库
"""
import logging
from typing import List, Dict

from neo4j import GraphDatabase

import config

logger = logging.getLogger(__name__)


class Neo4jStore:
    """Neo4j知识图谱存储"""

    def __init__(self):
        self.driver = None

    def connect(self):
        """建立Neo4j连接"""
        try:
            self.driver = GraphDatabase.driver(
                config.NEO4J_URI,
                auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
            )
            # 验证连接
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info(f"连接Neo4j成功: {config.NEO4J_URI}")
        except Exception as e:
            logger.error(f"连接Neo4j失败: {e}")
            raise

    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()

    def create_constraints(self):
        """创建唯一性约束"""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Artifact) REQUIRE a.object_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Museum) REQUIRE m.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Dynasty) REQUIRE d.name_en IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (ar:Artist) REQUIRE ar.name_en IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (mt:Material) REQUIRE mt.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (tp:ArtifactType) REQUIRE tp.name IS UNIQUE",
        ]
        with self.driver.session() as session:
            for c in constraints:
                try:
                    session.run(c)
                except Exception as e:
                    logger.debug(f"约束创建跳过: {e}")
        logger.info("创建约束完成")

    def import_artifacts(self, df, museum_name: str, dynasty_id_map: dict, dynasty_data: list):
        """
        将文物数据导入Neo4j
        创建节点：Artifact, Museum, Dynasty, Material, ArtifactType
        创建关系：STORED_IN, BELONGS_TO_DYNASTY, MADE_OF, CLASSIFIED_AS
        """
        if df.empty:
            return

        # 构建朝代ID到名称的映射
        id_to_dynasty = {d["id"]: d for d in dynasty_data}

        with self.driver.session() as session:
            # 1. 创建博物馆节点
            session.run(
                "MERGE (m:Museum {name: $name}) SET m.country = $country, m.city = $city",
                name=museum_name, country="United States", city="",
            )

            # 2. 批量创建文物节点和关系
            batch = []
            for _, row in df.iterrows():
                dynasty_name = row.get("dynasty", "")
                material = row.get("material", "")
                art_type = row.get("type", "")

                record = {
                    "object_id": str(row.get("object_id", "")),
                    "title_en": str(row.get("title_en", "")),
                    "title_zh": str(row.get("title_zh", "")),
                    "time_period": str(row.get("time_period", "")),
                    "dynasty": dynasty_name,
                    "material": material,
                    "art_type": art_type,
                    "description": str(row.get("description", ""))[:500],
                    "museum": museum_name,
                }
                batch.append(record)

                # 每200条执行一次
                if len(batch) >= 200:
                    self._batch_import(session, batch)
                    batch = []

            if batch:
                self._batch_import(session, batch)

        logger.info(f"Neo4j导入完成: {len(df)} 条文物 -> {museum_name}")

    def _batch_import(self, session, batch: List[Dict]):
        """批量导入文物数据到Neo4j"""
        # 使用UNWIND进行批量操作
        query = """
        UNWIND $batch AS item

        // 创建文物节点
        MERGE (a:Artifact {object_id: item.object_id})
        SET a.title_en = item.title_en,
            a.title_zh = item.title_zh,
            a.time_period = item.time_period,
            a.description = item.description

        // 关联博物馆
        WITH a, item
        MATCH (m:Museum {name: item.museum})
        MERGE (a)-[:STORED_IN]->(m)

        // 关联朝代
        WITH a, item
        WHERE item.dynasty IS NOT NULL AND item.dynasty <> ''
        MERGE (d:Dynasty {name_en: item.dynasty})
        MERGE (a)-[:BELONGS_TO_DYNASTY]->(d)

        // 关联材质
        WITH a, item
        WHERE item.material IS NOT NULL AND item.material <> ''
        MERGE (mt:Material {name: item.material})
        MERGE (a)-[:MADE_OF]->(mt)

        // 关联类型
        WITH a, item
        WHERE item.art_type IS NOT NULL AND item.art_type <> ''
        MERGE (tp:ArtifactType {name: item.art_type})
        MERGE (a)-[:CLASSIFIED_AS]->(tp)
        """
        session.run(query, batch=batch)

    def import_artists(self, artists_df):
        """导入艺术家节点和关系"""
        if artists_df.empty:
            return

        with self.driver.session() as session:
            batch = []
            for _, row in artists_df.iterrows():
                name_en = str(row.get("name_en", "")).strip()
                if not name_en:
                    continue
                batch.append({
                    "name_en": name_en,
                    "name_zh": str(row.get("name_zh", "")).strip(),
                })

                if len(batch) >= 200:
                    self._batch_import_artists(session, batch)
                    batch = []

            if batch:
                self._batch_import_artists(session, batch)

        logger.info(f"Neo4j艺术家导入: {len(artists_df)} 条")

    def _batch_import_artists(self, session, batch: List[Dict]):
        """批量导入艺术家"""
        query = """
        UNWIND $batch AS item
        MERGE (ar:Artist {name_en: item.name_en})
        SET ar.name_zh = item.name_zh
        """
        session.run(query, batch=batch)

    def link_artifacts_artists(self, df):
        """建立文物-艺术家关系"""
        if df.empty:
            return

        with self.driver.session() as session:
            batch = []
            for _, row in df.iterrows():
                object_id = str(row.get("object_id", "")).strip()
                artist_name = str(row.get("artist", "")).strip()
                if not object_id or not artist_name or artist_name.lower() in ("artist/maker unknown", "unknown", ""):
                    continue
                batch.append({
                    "object_id": object_id,
                    "artist_name": artist_name,
                })

                if len(batch) >= 200:
                    self._batch_link_artists(session, batch)
                    batch = []

            if batch:
                self._batch_link_artists(session, batch)

    def _batch_link_artists(self, session, batch: List[Dict]):
        """批量建立文物-艺术家关系"""
        query = """
        UNWIND $batch AS item
        MATCH (a:Artifact {object_id: item.object_id})
        MATCH (ar:Artist {name_en: item.artist_name})
        MERGE (a)-[:CREATED_BY]->(ar)
        """
        session.run(query, batch=batch)

    def create_dynasty_timeline(self, dynasty_data: list):
        """创建朝代时间线关系"""
        with self.driver.session() as session:
            for d in dynasty_data:
                session.run(
                    """
                    MERGE (d:Dynasty {name_en: $name_en})
                    SET d.name_zh = $name_zh,
                        d.start_year = $start_year,
                        d.end_year = $end_year
                    """,
                    name_en=d["name_en"],
                    name_zh=d["name_zh"],
                    start_year=d["start_year"],
                    end_year=d["end_year"],
                )
            # 创建朝代之间的"后继"关系
            sorted_dynasties = sorted(dynasty_data, key=lambda x: x.get("start_year", 0))
            for i in range(len(sorted_dynasties) - 1):
                d1 = sorted_dynasties[i]
                d2 = sorted_dynasties[i + 1]
                # 如果d2的起始年份在d1的结束年份附近，建立后继关系
                if abs(d2["start_year"] - d1["end_year"]) < 50:
                    session.run(
                        """
                        MATCH (d1:Dynasty {name_en: $name1})
                        MATCH (d2:Dynasty {name_en: $name2})
                        MERGE (d1)-[:SUCCEEDED_BY]->(d2)
                        """,
                        name1=d1["name_en"],
                        name2=d2["name_en"],
                    )
        logger.info("朝代时间线创建完成")

    def get_stats(self) -> Dict:
        """获取Neo4j中的节点和关系统计"""
        with self.driver.session() as session:
            result = session.run("""
                CALL {
                    MATCH (a:Artifact) RETURN count(a) AS artifacts
                }
                CALL {
                    MATCH (m:Museum) RETURN count(m) AS museums
                }
                CALL {
                    MATCH (d:Dynasty) RETURN count(d) AS dynasties
                }
                CALL {
                    MATCH (ar:Artist) RETURN count(ar) AS artists
                }
                CALL {
                    MATCH ()-[r]->() RETURN count(r) AS relationships
                }
                RETURN artifacts, museums, dynasties, artists, relationships
            """)
            record = result.single()
            return dict(record) if record else {}
