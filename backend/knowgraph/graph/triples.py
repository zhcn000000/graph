from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

from ..chat.chat_model import get_model
from .schema import (
    Entity,
    EntityType,
    ExtractedTriple,
    RelationshipType,
    get_entity_uri,
    get_relationship_uri,
)


class TripleStoreOperation(StrEnum):
    INSERT = "insert"
    DELETE = "delete"
    UPDATE = "update"
    UPSERT = "upsert"


@dataclass
class Triple:
    subject_uri: str
    predicate_uri: str
    object_uri: str
    subject_type: EntityType
    object_type: EntityType
    subject_name: str
    object_name: str
    properties: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    source: str | None = None

    def to_cypher(self) -> tuple[str, dict[str, Any]]:
        props = {
            "subject_uri": self.subject_uri,
            "predicate_uri": self.predicate_uri,
            "object_uri": self.object_uri,
            "subject_type": self.subject_type.value,
            "object_type": self.object_type.value,
            "subject_name": self.subject_name,
            "object_name": self.object_name,
            "created_at": self.created_at.isoformat(),
        }
        if self.description:
            props["description"] = self.description
        if self.source:
            props["source"] = self.source
        props.update(self.properties)

        cypher = """
        MATCH (s:{subject_type} {{uri: $subject_uri}})
        MATCH (o:{object_type} {{uri: $object_uri}})
        CREATE (s)-[r:{predicate} {{uri: $predicate_uri}}]->(o)
        SET r += $properties
        RETURN id(r) as edge_id
        """.format(
            subject_type=self.subject_type.value.capitalize(),
            object_type=self.object_type.value.capitalize(),
            predicate=self.predicate_uri.split("/")[-1],
        )
        return cypher, props

    def to_sparql(self) -> str:
        return f"""
        SELECT ?subject ?predicate ?object
        WHERE {{
            ?subject <{self.subject_uri}> ?predicate .
            ?predicate <{self.predicate_uri}> ?object .
            ?object <{self.object_uri}> ?value .
        }}
        """


@dataclass
class ArtifactTriple(Triple):
    def __init__(
        self,
        artifact_name: str,
        museum_name: str,
        dynasty_name: str | None = None,
        artist_name: str | None = None,
        material: str | None = None,
        artifact_type: str | None = None,
        description: str | None = None,
        properties: dict[str, Any] | None = None,
        source: str | None = None,
    ):
        self.artifact_name = artifact_name
        self.museum_name = museum_name
        self.dynasty_name = dynasty_name
        self.artist_name = artist_name
        self.material = material
        self.artifact_type = artifact_type

        subject_uri = get_entity_uri(EntityType.ARTIFACT, artifact_name)
        object_uri = get_entity_uri(EntityType.MUSEUM, museum_name)

        super().__init__(
            subject_uri=subject_uri,
            predicate_uri=get_relationship_uri(RelationshipType.COLLECTED_BY),
            object_uri=object_uri,
            subject_type=EntityType.ARTIFACT,
            object_type=EntityType.MUSEUM,
            subject_name=artifact_name,
            object_name=museum_name,
            properties=properties or {},
            description=description,
            source=source,
        )


class CSVRowInput(BaseModel):
    object_id: str
    title: str
    period: str | None = None
    type: str | None = None
    material: str | None = None
    description: str | None = None
    dimensions: str | None = None
    museum: str
    location: str | None = None
    detail_url: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    credit_line: str | None = None
    accession_number: str | None = None
    crawl_date: str | None = None

    def to_artifact_triples(self) -> list[ArtifactTriple]:
        triples = []
        props: dict[str, Any] = {}
        if self.object_id:
            props["object_id"] = self.object_id
        if self.period:
            props["period"] = self.period
        if self.type:
            props["artifact_type"] = self.type
        if self.material:
            props["material"] = self.material
        if self.dimensions:
            props["dimensions"] = self.dimensions
        if self.detail_url:
            props["detail_url"] = self.detail_url
        if self.image_url:
            props["image_url"] = self.image_url
        if self.credit_line:
            props["credit_line"] = self.credit_line
        if self.accession_number:
            props["accession_number"] = self.accession_number
        if self.crawl_date:
            props["crawl_date"] = self.crawl_date

        triple = ArtifactTriple(
            artifact_name=self.title,
            museum_name=self.museum,
            dynasty_name=self.period,
            material=self.material,
            artifact_type=self.type,
            description=self.description,
            properties=props,
            source=self.detail_url,
        )
        triples.append(triple)
        return triples


class LLMExtractor:
    SYSTEM_PROMPT = """你是一个专业的文物知识图谱专家，专门从海外博物馆的文物数据中提取结构化三元组信息。
你的任务是将文物记录转换为知识图谱三元组（主体-谓词-客体），遵循CIDOC-CRM本体标准。

## 实体类型
- artifact (文物): 具有唯一标识的名称
- museum (博物馆): 收藏文物的机构
- dynasty (朝代): 文物所属的历史朝代
- artist (艺术家): 文物的创作者
- location (地点): 博物馆所在地或文物出土地点

## 关系类型
- collected_by: 文物收藏于博物馆
- created_by: 文物由艺术家创作
- belongs_to_dynasty: 文物属于某个朝代
- made_of_material: 文物材质为某种材料
- is_type_of: 文物类型为某种类型
- located_at: 位置关系
- depicts: 描述/描绘
- related_to: 相关关系

## 输出要求
1. 从文物记录中提取所有可能的实体和关系
2. 对于每个实体，生成唯一的URI
3. 识别文物的年代、类型、材质等信息并建立相应关系
4. 如果信息不明确或缺失，使用"unknown"作为默认值
5. 用中文描述这个三元组代表的语义关系

## 三元组格式
每个三元组包含：
- subject: 主体实体
- predicate: 关系类型
- object: 客体实体
- description: 关系的语义描述（中文）
"""

    USER_PROMPT_TEMPLATE = """请从以下文物记录中提取知识图谱三元组：

{record}

请以JSON数组格式输出所有提取的三元组，每条记录包含：
- subject: 主体实体 {name, entity_type, properties, description}
- predicate: 关系类型
- object: 客体实体 {name, entity_type, properties, description}
- description: 关系的语义描述（中文）

只输出JSON，不要包含其他文字。"""

    def __init__(self, model_name: str | None = None):
        self.model = get_model(model_name)

    async def aextract_from_csv_row(self, row: CSVRowInput) -> list[ExtractedTriple]:
        record_str = json.dumps(row.model_dump(), ensure_ascii=False, indent=2)
        user_prompt = self.USER_PROMPT_TEMPLATE.format(record=record_str)

        from pydantic_ai import Agent

        from ..chat.struct import ModelDeps

        agent: Agent[ModelDeps, list[ExtractedTriple]] = Agent(
            model=self.model,
            deps_type=ModelDeps,
            output_type=list[ExtractedTriple],
            instructions=self.SYSTEM_PROMPT,
            output_retries=3,
        )  # type: ignore

        result = await agent.run(user_prompt)
        return result.output

    async def aextract_from_csv(self, csv_path: str) -> list[ExtractedTriple]:
        df = pd.read_csv(csv_path)
        all_triples = []

        for _, row in df.iterrows():
            try:
                row_input = CSVRowInput(**row.to_dict())
                triples = await self.aextract_from_csv_row(row_input)
                all_triples.extend(triples)
            except Exception:
                continue

        return all_triples

    async def aextract_from_dataframe(self, df: pd.DataFrame) -> list[ExtractedTriple]:
        all_triples = []

        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                row_input = CSVRowInput(**{k: v for k, v in row_dict.items() if pd.notna(v)})
                triples = await self.aextract_from_csv_row(row_input)
                all_triples.extend(triples)
            except Exception:
                continue

        return all_triples


class TripleStore:
    def __init__(self, graph_name: str = "artifact_graph"):
        self.graph_name = graph_name

    def _build_cypher_vertex_label(self, entity_type: EntityType) -> str:
        return entity_type.value.capitalize()

    def _build_cypher_edge_label(self, rel_type: RelationshipType) -> str:
        return rel_type.value

    def build_create_vertex_cypher(
        self,
        entity: Entity,
    ) -> tuple[str, dict[str, Any]]:
        label = self._build_cypher_vertex_label(entity.entity_type)
        props = {
            "uri": entity.uri,
            "name": entity.name,
            "entity_type": entity.entity_type.value,
        }
        if entity.description:
            props["description"] = entity.description
        props.update(entity.properties)

        cypher = f"CREATE (v:{label} {{uri: $uri, name: $name, entity_type: $entity_type}})"
        if props:
            props_str = ", ".join([f"{k}: ${k}" for k in props])
            cypher += f" SET {props_str}"

        cypher += " RETURN id(v) as vertex_id"
        return cypher, props

    def build_create_edge_cypher(
        self,
        triple: Triple,
    ) -> tuple[str, dict[str, Any]]:
        subject_label = self._build_cypher_vertex_label(triple.subject_type)
        object_label = self._build_cypher_vertex_label(triple.object_type)
        edge_label = self._build_cypher_edge_label(RelationshipType(triple.predicate_uri.split("/")[-1]))

        props = {
            "subject_uri": triple.subject_uri,
            "object_uri": triple.object_uri,
            "predicate_uri": triple.predicate_uri,
            "subject_name": triple.subject_name,
            "object_name": triple.object_name,
            "created_at": triple.created_at.isoformat(),
        }
        if triple.description:
            props["description"] = triple.description
        if triple.source:
            props["source"] = triple.source
        props.update(triple.properties)

        cypher = f"""
        MATCH (s:{subject_label} {{uri: $subject_uri}})
        MATCH (o:{object_label} {{uri: $object_uri}})
        CREATE (s)-[r:{edge_label} {{uri: $predicate_uri}}]->(o)
        SET r += ${{props}}
        RETURN id(r) as edge_id
        """
        return cypher, {"props": props}

    def build_match_vertex_cypher(
        self,
        entity_uri: str | None = None,
        entity_type: EntityType | None = None,
        name: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        label = self._build_cypher_vertex_label(entity_type) if entity_type else None
        conditions = []
        params = {}

        if entity_uri:
            conditions.append("v.uri = $uri")
            params["uri"] = entity_uri
        if name:
            conditions.append("v.name = $name")
            params["name"] = name

        where_clause = " AND ".join(conditions) if conditions else "true"
        label_clause = f":{label}" if label else ""

        cypher = f"MATCH (v{label_clause} {{{where_clause}}}) RETURN v"
        return cypher, params

    def build_match_edge_cypher(
        self,
        subject_uri: str | None = None,
        object_uri: str | None = None,
        predicate_uri: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        conditions = []
        params = {}

        if subject_uri:
            conditions.append("startNode(r).uri = $subject_uri")
            params["subject_uri"] = subject_uri
        if object_uri:
            conditions.append("endNode(r).uri = $object_uri")
            params["object_uri"] = object_uri
        if predicate_uri:
            conditions.append("type(r) = $predicate_uri")
            params["predicate_uri"] = predicate_uri.split("/")[-1]

        where_clause = " AND ".join(conditions) if conditions else "true"

        cypher = f"MATCH (s)-[r]->(o) WHERE {where_clause} RETURN r, startNode(r) as s, endNode(r) as o"
        return cypher, params

    def build_delete_vertex_cypher(
        self,
        entity_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        cypher = "MATCH (v {uri: $uri}) DETACH DELETE v RETURN count(*) as deleted_count"
        return cypher, {"uri": entity_uri}

    def build_delete_edge_cypher(
        self,
        subject_uri: str,
        object_uri: str,
        predicate_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        predicate_name = predicate_uri.rsplit("/", maxsplit=1)[-1]
        cypher = f"""
        MATCH (s {{uri: $subject_uri}})-[r:{predicate_name}]->(o {{uri: $object_uri}})
        DELETE r
        RETURN count(*) as deleted_count
        """
        return cypher, {"subject_uri": subject_uri, "object_uri": object_uri}

    def build_update_vertex_cypher(
        self,
        entity_uri: str,
        properties: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        props_set = ", ".join([f"v.{k} = ${k}" for k in properties])
        cypher = f"MATCH (v {{uri: $uri}}) SET {props_set} RETURN v"
        params = {"uri": entity_uri}
        params.update(properties)
        return cypher, params

    def build_update_edge_cypher(
        self,
        subject_uri: str,
        object_uri: str,
        predicate_uri: str,
        properties: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        predicate_name = predicate_uri.rsplit("/", maxsplit=1)[-1]
        props_set = ", ".join([f"r.{k} = ${k}" for k in properties])
        cypher = f"""
        MATCH (s {{uri: $subject_uri}})-[r:{predicate_name}]->(o {{uri: $object_uri}})
        SET {props_set}
        RETURN r
        """
        params = {"subject_uri": subject_uri, "object_uri": object_uri}
        params.update(properties)
        return cypher, params

    def build_upsert_vertex_cypher(
        self,
        entity: Entity,
    ) -> tuple[str, dict[str, Any]]:
        label = self._build_cypher_vertex_label(entity.entity_type)
        props = {
            "uri": entity.uri,
            "name": entity.name,
            "entity_type": entity.entity_type.value,
        }
        if entity.description:
            props["description"] = entity.description
        props.update(entity.properties)

        props_str = ", ".join([f"{k}: ${k}" for k in props])

        cypher = f"""
        MERGE (v:{label} {{uri: $uri}})
        ON CREATE SET v.name = $name, v.entity_type = $entity_type
        ON MATCH SET v.name = $name, v.entity_type = $entity_type
        SET v += ${props_str}
        RETURN id(v) as vertex_id
        """
        return cypher, props

    def build_upsert_edge_cypher(
        self,
        triple: Triple,
    ) -> tuple[str, dict[str, Any]]:
        subject_label = self._build_cypher_vertex_label(triple.subject_type)
        object_label = self._build_cypher_vertex_label(triple.object_type)
        edge_label = self._build_cypher_edge_label(RelationshipType(triple.predicate_uri.split("/")[-1]))

        props = {
            "subject_uri": triple.subject_uri,
            "object_uri": triple.object_uri,
            "predicate_uri": triple.predicate_uri,
            "subject_name": triple.subject_name,
            "object_name": triple.object_name,
            "created_at": triple.created_at.isoformat(),
        }
        if triple.description:
            props["description"] = triple.description
        if triple.source:
            props["source"] = triple.source
        props.update(triple.properties)

        cypher = f"""
        MATCH (s:{subject_label} {{uri: $subject_uri}})
        MATCH (o:{object_label} {{uri: $object_uri}})
        MERGE (s)-[r:{edge_label}]->(o)
        ON CREATE SET r.uri = $predicate_uri, r.subject_name = $subject_name, r.object_name = $object_name
        ON MATCH SET r.uri = $predicate_uri, r.subject_name = $subject_name, r.object_name = $object_name
        SET r += ${{props}}
        RETURN id(r) as edge_id
        """
        return cypher, {"props": props}

    def build_traverse_cypher(
        self,
        start_uri: str,
        max_hops: int = 3,
        direction: Literal["outbound", "inbound", "both"] = "both",
    ) -> tuple[str, dict[str, Any]]:
        if direction == "outbound":
            rel_pattern = "-[r]->"
        elif direction == "inbound":
            rel_pattern = "<-[r]-"
        else:
            rel_pattern = "-[r]-"

        cypher = f"""
        MATCH path = (start {{uri: $start_uri}}){rel_pattern}*(1..{max_hops})(end)
        WITH nodes(path) as nodes, rels(path) as rels
        UNWIND range(0, size(nodes) - 1) as idx
        WITH nodes[idx] as node, rels[idx] as rel, idx
        WHERE rel IS NOT NULL
        RETURN startNode(rel) as source, type(rel) as relationship, endNode(rel) as target, rel.uri as rel_uri
        """
        return cypher, {"start_uri": start_uri, "max_hops": max_hops}

    def build_shortest_path_cypher(
        self,
        start_uri: str,
        end_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        cypher = """
        MATCH path = shortestPath((start {uri: $start_uri})-[*]->(end {uri: $end_uri}))
        WITH nodes(path) as nodes, rels(path) as rels
        UNWIND range(0, size(nodes) - 1) as idx
        WITH nodes[idx] as node, rels[idx] as rel, idx
        RETURN idx, node.uri as node_uri, node.name as node_name,
               CASE WHEN rel IS NOT NULL THEN type(rel) ELSE NULL END as relationship,
               CASE WHEN rel IS NOT NULL THEN rel.uri ELSE NULL END as rel_uri
        ORDER BY idx
        """
        return cypher, {"start_uri": start_uri, "end_uri": end_uri}
