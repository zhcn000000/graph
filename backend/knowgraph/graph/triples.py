from asyncer import create_task_group
from pydantic_ai import ModelSettings

from ..chat.model import agent
from ..chat.struct import ModelDeps
from ..documents.embedder import arerank_scores
from ..documents.models import Document
from . import schema
from .schema import (
    EntityType,
    ExtractedTriple,
)


def _format_pre_extracted_triples(triples: list[ExtractedTriple]) -> str:
    if not triples:
        return ""
    lines = ["已知三元组（请勿重复提取）："]
    for t in triples:
        desc = f" — {t.description}" if t.description else ""
        lines.append(f"  ({t.subject.name}) -[{t.predicate.predicate}]-> ({t.object.name}){desc}")
    return "\n".join(lines)


async def compute_triples_strength(
    triples: list[ExtractedTriple],
) -> list[ExtractedTriple]:
    if not triples:
        return triples

    groups: dict[str, list[tuple[int, ExtractedTriple]]] = {}
    for idx, t in enumerate(triples):
        if t.subject.entity_type != EntityType.ARTIFACT:
            continue
        key = f"{t.subject.name}::{t.subject.entity_type.value}"
        groups.setdefault(key, []).append((idx, t))

    async def rerank_group(items: list[tuple[int, ExtractedTriple]]) -> None:
        subject = items[0][1].subject
        query = f"{subject.name} {subject.description or ''}".strip()
        edge_docs = [
            Document(
                content=f"{t.predicate.predicate.value} {t.object.name} "
                f"{t.object.description or ''} {t.description or ''}".strip(),
            )
            for _, t in items
        ]
        score_map = await arerank_scores(query, edge_docs)
        for local_idx, (global_idx, _) in enumerate(items):
            score = score_map.get(local_idx)
            if score is not None:
                triples[global_idx].predicate.strength = score

    if groups:
        async with create_task_group() as tg:
            for items in groups.values():
                tg.soonify(rerank_group)(items)

    return triples


async def compute_triples_strength_batch(
    doc_triples_list: list[list[ExtractedTriple]],
) -> None:
    tasks_data = [triples for triples in doc_triples_list if triples]
    if not tasks_data:
        return

    async with create_task_group() as tg:
        tasks = [tg.soonify(compute_triples_strength)(triples) for triples in tasks_data]

    for task in tasks:
        _ = task.value


_TYPE_EXAMPLE_TEXTS: dict[EntityType, str] = {
    EntityType.ARTIFACT_TYPE: "\n".join(schema._KNOWN_ARTIFACT_TYPES),
    EntityType.MATERIAL: "\n".join(schema._KNOWN_MATERIALS),
    EntityType.DYNASTY: "\n".join(schema._KNOWN_DYNASTIES),
}

_CLASSIFIABLE_TYPES_ORDERED: list[EntityType] = [
    EntityType.ARTIFACT_TYPE,
    EntityType.MATERIAL,
    EntityType.DYNASTY,
]


async def aclassify_entity_type(
    name: str,
    description: str | None = None,
) -> EntityType | None:
    query = f"{name} {description or ''}".strip()
    documents = [_TYPE_EXAMPLE_TEXTS[t] for t in _CLASSIFIABLE_TYPES_ORDERED]

    try:
        score_map = await arerank_scores(query, documents, force_text=True)
    except Exception:
        return None

    best_type: EntityType | None = None
    best_score = float("-inf")
    for idx, entity_type in enumerate(_CLASSIFIABLE_TYPES_ORDERED):
        score = score_map.get(idx)
        if score is not None and score > best_score:
            best_score = score
            best_type = entity_type

    return best_type


async def classify_entity_types_for_triples(
    triples: list[ExtractedTriple],
) -> None:
    if not triples:
        return

    to_classify: dict[tuple[str, EntityType], str | None] = {}
    for t in triples:
        for entity in (t.subject, t.object):
            if entity.entity_type not in schema.CLASSIFIABLE_ENTITY_TYPES:
                continue
            key = (entity.canonical_name, entity.entity_type)
            if key not in to_classify:
                to_classify[key] = entity.description

    if not to_classify:
        return

    type_lookup: dict[tuple[str, EntityType], EntityType | None] = {}

    async def classify_one(key: tuple[str, EntityType], desc: str | None) -> None:
        cname, _ = key
        result = await aclassify_entity_type(cname, desc)
        type_lookup[key] = result

    async with create_task_group() as tg:
        for key, desc in to_classify.items():
            tg.soonify(classify_one)(key, desc)

    for t in triples:
        for entity in (t.subject, t.object):
            if entity.entity_type not in schema.CLASSIFIABLE_ENTITY_TYPES:
                continue
            key = (entity.canonical_name, entity.entity_type)
            classified = type_lookup.get(key)
            if classified is not None and classified != entity.entity_type:
                entity.entity_type = classified


async def classify_entity_types_batch(
    doc_triples_list: list[list[ExtractedTriple]],
) -> None:
    tasks_data = [triples for triples in doc_triples_list if triples]
    if not tasks_data:
        return

    async with create_task_group() as tg:
        tasks = [tg.soonify(classify_entity_types_for_triples)(triples) for triples in tasks_data]

    for task in tasks:
        _ = task.value


class LLMExtractor:
    SYSTEM_PROMPT = """你是一个专业的文物知识图谱专家，专门从海外博物馆的文物数据中提取结构化三元组信息。
你的任务是将文物记录转换为知识图谱三元组（主体-谓词-客体），遵循CIDOC-CRM本体标准。
你无需提取关系中的strength字段，设置为null获不填即可，后续会根据三元组文本内容进行相关性计算来赋值strength。
如果文物记录中的信息不完整或你怀疑有错（如缺少朝代、材质、艺术家等），
你可以结合自身知识或必要时使用 search_web 工具进行网络搜索来补充缺失的上下文信息，
确保提取的三元组尽可能准确和完整。其中，subject总是应该是文物，

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
3. 如果信息不明确或缺失，可以使用 search_web 搜索相关信息后再提取
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
- subject: 主体实体 {{name, entity_type, properties, description}}
- predicate: 关系类型字符串 (如 "collected_by", "belongs_to_dynasty" 等)
- object: 客体实体 {{name, entity_type, properties, description}}
- description: 关系的语义描述（中文）

只输出JSON，不要包含其他文字。"""

    async def aextract_from_document(self, doc: Document) -> list[ExtractedTriple]:
        user_prompt = self._build_user_prompt(doc.content, doc.triples)
        return await self._run_agent_with_prompt(user_prompt)

    def _build_user_prompt(self, record: str, pre_triples: list[ExtractedTriple]) -> str:
        known_str = _format_pre_extracted_triples(pre_triples)
        return self.USER_PROMPT_TEMPLATE.format(record=record, known_triples=known_str)

    async def _run_agent_with_prompt(self, prompt: str) -> list[ExtractedTriple]:
        result = await agent.run(
            prompt,
            instructions=self.SYSTEM_PROMPT,
            deps=ModelDeps(select_toolset={"web_toolkit"}),
            model_settings=ModelSettings(extra_body={"thinking": {"type": "disabled"}}),
            output_type=list[ExtractedTriple],
        )
        return result.output
