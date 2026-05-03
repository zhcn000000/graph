import json
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import pandas as pd
from pydantic import BaseModel
from pydantic_ai import Agent

from ..chat.chat_model import get_model
from ..chat.struct import ModelDeps
from ..documents.models import Document
from .schema import (
    EntityType,
    ExtractedTriple,
    RelationshipType,
    get_entity_uri,
    get_relationship_uri,
)


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
    credit_line: str | None = None
    accession_number: str | None = None
    crawl_date: str | None = None

    def to_artifact_triples(self) -> list[Triple]:
        triples: list[Triple] = []
        props: dict[str, Any] = {
            "object_id": self.object_id,
            "period": self.period,
            "artifact_type": self.type,
            "material": self.material,
            "dimensions": self.dimensions,
            "detail_url": self.detail_url,
            "image_url": self.image_url,
            "credit_line": self.credit_line,
            "accession_number": self.accession_number,
            "crawl_date": self.crawl_date,
            "museum": self.museum,
            "location": self.location,
            "title": self.title,
        }
        props = {k: v for k, v in props.items() if v}

        artifact_uri = get_entity_uri(EntityType.ARTIFACT, self.title)

        if self.museum:
            triples.append(
                ArtifactTriple(
                    artifact_name=self.title,
                    museum_name=self.museum,
                    description=self.description,
                    properties=props,
                    source=self.detail_url,
                ),
            )

        if self.period:
            triples.append(
                Triple(
                    subject_uri=artifact_uri,
                    predicate_uri=get_relationship_uri(RelationshipType.BELONGS_TO_DYNASTY),
                    object_uri=get_entity_uri(EntityType.DYNASTY, self.period),
                    subject_type=EntityType.ARTIFACT,
                    object_type=EntityType.DYNASTY,
                    subject_name=self.title,
                    object_name=self.period,
                    description=f"{self.title} 属于 {self.period}",
                    properties=props,
                    source=self.detail_url,
                ),
            )

        if self.material:
            triples.append(
                Triple(
                    subject_uri=artifact_uri,
                    predicate_uri=get_relationship_uri(RelationshipType.MADE_OF_MATERIAL),
                    object_uri=get_entity_uri(EntityType.ARTIFACT, self.material),
                    subject_type=EntityType.ARTIFACT,
                    object_type=EntityType.ARTIFACT,
                    subject_name=self.title,
                    object_name=self.material,
                    description=f"{self.title} 材质为 {self.material}",
                    properties=props,
                    source=self.detail_url,
                ),
            )

        if self.type:
            triples.append(
                Triple(
                    subject_uri=artifact_uri,
                    predicate_uri=get_relationship_uri(RelationshipType.IS_TYPE_OF),
                    object_uri=get_entity_uri(EntityType.ARTIFACT, self.type),
                    subject_type=EntityType.ARTIFACT,
                    object_type=EntityType.ARTIFACT,
                    subject_name=self.title,
                    object_name=self.type,
                    description=f"{self.title} 类型为 {self.type}",
                    properties=props,
                    source=self.detail_url,
                ),
            )

        if self.location and self.museum:
            triples.append(
                Triple(
                    subject_uri=get_entity_uri(EntityType.MUSEUM, self.museum),
                    predicate_uri=get_relationship_uri(RelationshipType.LOCATED_AT),
                    object_uri=get_entity_uri(EntityType.LOCATION, self.location),
                    subject_type=EntityType.MUSEUM,
                    object_type=EntityType.LOCATION,
                    subject_name=self.museum,
                    object_name=self.location,
                    description=f"{self.museum} 位于 {self.location}",
                    properties=props,
                    source=self.detail_url,
                ),
            )

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
        self._agent = self._create_agent()

    def _create_agent(self) -> Agent[ModelDeps, list[ExtractedTriple]]:
        from pydantic_ai import Agent

        return cast(
            Agent[ModelDeps, list[ExtractedTriple]],
            Agent(
                model=self.model,
                deps_type=ModelDeps,
                output_type=list[ExtractedTriple],
                instructions=self.SYSTEM_PROMPT,
                output_retries=3,
            ),
        )

    async def aextract_from_csv_row(self, row: CSVRowInput) -> list[ExtractedTriple]:
        record_str = json.dumps(row.model_dump(), ensure_ascii=False, indent=2)
        user_prompt = self.USER_PROMPT_TEMPLATE.format(record=record_str)
        result = await self._agent.run(user_prompt, deps=ModelDeps(select_toolset=[]))
        return result.output

    async def aextract_from_document(self, doc: Document) -> list[ExtractedTriple]:
        user_prompt = self.USER_PROMPT_TEMPLATE.format(record=doc.content)
        result = await self._agent.run(user_prompt, deps=ModelDeps(select_toolset=[]))
        return result.output

    async def aextract_from_csv(self, csv_path: str) -> list[ExtractedTriple]:
        df = pd.read_csv(csv_path)
        return await self.aextract_from_dataframe(df)

    async def aextract_from_dataframe(self, df: pd.DataFrame) -> list[ExtractedTriple]:
        all_triples = []

        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                row_input = CSVRowInput(**{k: v for k, v in row_dict.items() if pd.notna(v)})
                triples = await self.aextract_from_csv_row(row_input)
                all_triples.extend(triples)
            except Exception as e:
                warnings.warn(f"Skipping row due to extraction failure: {e}", UserWarning, stacklevel=2)
                continue

        return all_triples
