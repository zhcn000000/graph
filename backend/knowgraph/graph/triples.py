from pydantic_ai import ModelSettings

from ..chat.model import agent
from ..chat.struct import ModelDeps
from ..documents.embedder import arerank_scores
from ..documents.models import Document
from .schema import (
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
    score_map = await arerank_scores(combined_query, edge_docs)
    for idx, t in enumerate(triples):
        score = score_map.get(idx)
        if score is not None:
            t.predicate.strength = score
    return triples


class LLMExtractor:
    SYSTEM_PROMPT = """你是一个专业的文物知识图谱专家，专门从海外博物馆的文物数据中提取结构化三元组信息。
你的任务是将文物记录转换为知识图谱三元组（主体-谓词-客体），遵循CIDOC-CRM本体标准。
你无需提取关系中的strength字段，设置为null获不填即可，后续会根据三元组文本内容进行相关性计算来赋值strength。
如果文物记录中的信息不完整或你怀疑有错（如缺少朝代、材质、艺术家等），
你可以结合自身知识或必要时使用 search_web 工具进行网络搜索来补充缺失的上下文信息，
确保提取的三元组尽可能准确和完整。

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
