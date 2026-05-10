import json
import warnings

import pandas as pd
from pydantic import BaseModel
from pydantic_ai import ModelSettings

from ..chat.model import agent
from ..chat.struct import ModelDeps
from ..documents.embedder import arerank_documents
from ..documents.models import Document
from .schema import (
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipInfo,
    RelationshipType,
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

    def to_artifact_triples(self) -> list[ExtractedTriple]:
        triples: list[ExtractedTriple] = []

        if self.museum:
            triples.append(
                ExtractedTriple(
                    subject=ExtractedEntity(name=self.title, entity_type=EntityType.ARTIFACT),
                    predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
                    object=ExtractedEntity(name=self.museum, entity_type=EntityType.MUSEUM),
                    description=self.description or f"{self.title} 收藏于 {self.museum}",
                ),
            )

        if self.period:
            triples.append(
                ExtractedTriple(
                    subject=ExtractedEntity(name=self.title, entity_type=EntityType.ARTIFACT),
                    predicate=RelationshipInfo(predicate=RelationshipType.BELONGS_TO_DYNASTY),
                    object=ExtractedEntity(name=self.period, entity_type=EntityType.DYNASTY),
                    description=f"{self.title} 属于 {self.period}",
                ),
            )

        if self.material:
            triples.append(
                ExtractedTriple(
                    subject=ExtractedEntity(name=self.title, entity_type=EntityType.ARTIFACT),
                    predicate=RelationshipInfo(predicate=RelationshipType.MADE_OF_MATERIAL),
                    object=ExtractedEntity(name=self.material, entity_type=EntityType.MATERIAL),
                    description=f"{self.title} 材质为 {self.material}",
                ),
            )

        if self.type:
            triples.append(
                ExtractedTriple(
                    subject=ExtractedEntity(name=self.title, entity_type=EntityType.ARTIFACT),
                    predicate=RelationshipInfo(predicate=RelationshipType.IS_TYPE_OF),
                    object=ExtractedEntity(name=self.type, entity_type=EntityType.ARTIFACT_TYPE),
                    description=f"{self.title} 类型为 {self.type}",
                ),
            )

        if self.location and self.museum:
            triples.append(
                ExtractedTriple(
                    subject=ExtractedEntity(name=self.museum, entity_type=EntityType.MUSEUM),
                    predicate=RelationshipInfo(predicate=RelationshipType.LOCATED_AT),
                    object=ExtractedEntity(name=self.location, entity_type=EntityType.LOCATION),
                    description=f"{self.museum} 位于 {self.location}",
                ),
            )

        return triples


def _format_pre_extracted_triples(triples: list[ExtractedTriple]) -> str:
    if not triples:
        return ""
    lines = ["已知三元组（请勿重复提取）："]
    for t in triples:
        desc = f" — {t.description}" if t.description else ""
        lines.append(f"  ({t.subject.name}) -[{t.predicate.predicate}]-> ({t.object.name}){desc}")
    return "\n".join(lines)


def _build_edge_query_from_triple(t: ExtractedTriple) -> str:
    parts = [f"{t.subject.name}", f"{t.predicate.predicate.replace('_', ' ')}", f"{t.object.name}"]
    if t.description:
        parts.append(f"({t.description})")
    return " ".join(parts)


async def compute_triples_strength(
    triples: list[ExtractedTriple],
    topn: int = 200,
) -> list[ExtractedTriple]:
    if not triples:
        return triples
    combined_query = " ".join([_build_edge_query_from_triple(t) for t in triples])
    edge_docs = [Document(content=_build_edge_query_from_triple(t)) for t in triples]
    reranked = await arerank_documents(combined_query, edge_docs, topn=topn, skip_sorting=True)
    for t, rd in zip(triples, reranked, strict=True):
        if rd.query_score is not None:
            t.predicate.strength = rd.query_score
    return triples


class LLMExtractor:
    SYSTEM_PROMPT = """你是一个专业的文物知识图谱专家，专门从海外博物馆的文物数据中提取结构化三元组信息。
你的任务是将文物记录转换为知识图谱三元组（主体-谓词-客体），遵循CIDOC-CRM本体标准。
你无需提取关系中的strength字段，设置为null获不填即可，后续会根据三元组文本内容进行相关性计算来赋值strength。
## 实体类型
- artifact (文物): 具有唯一标识的名称
- museum (博物馆): 收藏文物的机构
- dynasty (朝代): 文物所属的历史朝代
- artist (艺术家): 文物的创作者
- location (地点): 博物馆所在地或文物出土地点
- material (材料): 文物的材质，如青铜、丝绸、陶瓷等
- artifact_type (文物类型): 文物的类型分类，如绘画、雕塑、陶瓷等

## 关系类型
- collected_by: 文物收藏于博物馆
- created_by: 文物由艺术家创作
- belongs_to_dynasty: 文物属于某个朝代
- made_of_material: 文物使用某种材质制作
- is_type_of: 文物属于某种类型
- located_at: 位置关系
- depicts: 描述/描绘
- related_to: 相关关系

## 输出要求
1. 优先关注已有三元组未覆盖的实体和关系
2. 对于每个实体，生成唯一的URI
3. 如果信息不明确或缺失，跳过该实体
4. 用中文描述这个三元组代表的语义关系

## 三元组格式
每个三元组包含：
- subject: 主体实体
- predicate: 关系类型 (predicate 字段直接填关系名称，如 "collected_by")
- object: 客体实体
- description: 关系的语义描述（中文）
"""

    USER_PROMPT_TEMPLATE = """{known_triples}
请从以下文物记录中提取**额外**的知识图谱三元组：

{record}

请以JSON数组格式输出所有提取的三元组，每条记录包含：
- subject: 主体实体 {name, entity_type, properties, description}
- predicate: 关系类型字符串 (如 "collected_by", "belongs_to_dynasty" 等)
- object: 客体实体 {name, entity_type, properties, description}
- description: 关系的语义描述（中文）

只输出JSON，不要包含其他文字。"""

    async def aextract_from_csv_row(self, row: CSVRowInput) -> list[ExtractedTriple]:
        record_str = json.dumps(row.model_dump(), ensure_ascii=False, indent=2)
        user_prompt = self._build_user_prompt(record_str, [])
        triples = await self._run_agent_with_prompt(user_prompt)
        return await compute_triples_strength(triples)

    async def aextract_from_document(self, doc: Document) -> list[ExtractedTriple]:
        pre_triples = [t for t in doc.triples if t.predicate.strength is None]
        if pre_triples:
            await compute_triples_strength(pre_triples)

        user_prompt = self._build_user_prompt(doc.content, doc.triples)
        triples = await self._run_agent_with_prompt(user_prompt)
        return await compute_triples_strength(triples)

    def _build_user_prompt(self, record: str, pre_triples: list[ExtractedTriple]) -> str:
        known_str = _format_pre_extracted_triples(pre_triples)
        return self.USER_PROMPT_TEMPLATE.format(record=record, known_triples=known_str)

    async def _run_agent_with_prompt(self, prompt: str) -> list[ExtractedTriple]:

        result = await agent.run(
            prompt,
            deps=ModelDeps(),
            model_settings=ModelSettings(
                extra_body={"thinking": {"type": "disabled"}},
            ),
            output_type=list[ExtractedTriple],
        )
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
