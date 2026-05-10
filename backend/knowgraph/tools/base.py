from functools import cache
from typing import Literal
from uuid import UUID

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from pydantic_monty import Monty
from rich.pretty import pretty_repr
from tavily import AsyncTavilyClient

from knowgraph.database.ragmode import RAGMode
from knowgraph.graph.schema import EntityType, ExtractedEntity

rag_mode = RAGMode()


async def search_documents_base(
    queries: list[str],
    regex: str | None = None,
    file_ids: list[str] | None = None,
    offset: int = 0,
    use_graph: bool = True,
) -> str:
    uuids = [UUID(fid) for fid in file_ids] if file_ids else None
    docs, graph_entities = await rag_mode.ahyprid_search(
        queries=queries,
        k=8,
        regex=regex,
        file_ids=uuids,
        use_graph=use_graph,
        max_hops=2,
        offset=offset,
    )

    if not docs:
        offset_info = f" (第{offset + 1}条起)" if offset else ""
        return f"## 搜索结果{offset_info}\n\n查询: {queries}\n\n未找到相关文档。"

    data = []
    for i, doc in enumerate(docs):
        score = doc.query_score if doc.query_score is not None else 0.0
        source = doc.name or "unknown"
        preview = doc.content[:300] + "..." if len(doc.content) > 300 else doc.content
        row = {
            "#": offset + i + 1,
            "来源": source,
            "内容预览": preview,
            "相关性%": f"{min(score, 1.0) * 100:.1f}",
        }
        if doc.document_index is not None:
            row["文档ID"] = str(doc.document_index)
            row["分块"] = doc.chunk_index if doc.chunk_index is not None else "-"
        data.append(row)

    md = "## 搜索结果\n\n"
    md += f"查询: {queries}\n"
    if offset:
        md += f"分页: 第{offset + 1}-{offset + len(docs)}条\n"
    md += f"共 {len(docs)} 条结果\n\n"

    if graph_entities:
        md += "### 相关实体\n"
        for g in graph_entities[:10]:
            md += f"- **{g.entity_name}** ({g.entity_type}) `{g.entity_uri}`\n"
        md += "\n"

    dff = pd.DataFrame(data)
    md += dff.to_markdown(index=False)
    md += f"\n\n> 提示: 使用 `offset={offset + len(docs)}` 翻页查看更多结果。"
    md += "\n> 使用 `get_document_context` 通过文档ID获取更多上下文分块。"
    md += "\n> 使用 `get_document_entities` 通过文档ID查询相关图实体。"

    return md


async def traverse_graph_base(
    entity_uris: list[str],
    max_hops: int = 2,
    direction: str = "both",
) -> str:
    graph = await rag_mode.graph_manager.atraverse_multi(entity_uris, max_hops=max_hops, direction=direction)

    if graph.number_of_nodes() == 0:
        return "## 图谱遍历结果\n\n未找到相关实体或关系。"

    nodes_data = []
    for node_key, data in graph.nodes(data=True):
        entity_type = str(data.get("entity_type", ""))
        name = str(data.get("name", str(node_key)))
        uri: str
        if entity_type and name:
            uri = str(ExtractedEntity(name=name, entity_type=EntityType(entity_type)).uri)
        else:
            uri = str(node_key)
        nodes_data.append({
            "名称": name,
            "类型": entity_type,
            "URI": uri,
        })

    edges_data = []
    for u, v, edata in graph.edges(data=True):
        s_name = graph.nodes[u].get("name", u)
        o_name = graph.nodes[v].get("name", v)
        rel = edata.get("label", "related_to")
        desc = edata.get("description", "")
        edges_data.append({
            "主体": s_name,
            "关系": rel,
            "客体": o_name,
            "描述": desc or "",
        })

    md = "## 图谱遍历结果\n\n"
    md += f"遍历: {len(entity_uris)}个起始实体, {max_hops}跳, 方向={direction}\n"

    if nodes_data:
        md += f"\n### 实体 ({len(nodes_data)})\n"
        dff_nodes = pd.DataFrame(nodes_data)
        md += dff_nodes.to_markdown(index=False)

    if edges_data:
        md += f"\n### 关系 ({len(edges_data)})\n"
        dff_edges = pd.DataFrame(edges_data)
        md += dff_edges.to_markdown(index=False)

    md += "\n> 提示: 使用 `get_entity_info` 查看特定实体详情,或使用 `search_documents` 搜索实体相关文档。"

    return md


async def get_entity_info_base(uri: str) -> str:
    vertex = await rag_mode.graph_manager.aget_vertex(uri)

    if vertex is None:
        return f"## 实体详情\n\n未找到URI为 `{uri}` 的实体。"

    context = await rag_mode.graph_manager.aexpand_context(uri, max_hops=1, direction="both")

    md = "## 实体详情\n\n"
    md += f"**名称**: {vertex.get('name', 'unknown')}\n"
    md += f"**类型**: {vertex.get('entity_type', 'unknown')}\n"
    md += f"**URI**: `{vertex.get('uri', uri)}`\n"

    if vertex.get("description"):
        md += f"**描述**: {vertex['description']}\n"

    extra = {k: v for k, v in vertex.items() if k not in {"id", "label", "uri", "name", "entity_type", "description"}}
    if extra:
        md += "\n**属性**:\n"
        for k, v in extra.items():
            md += f"- {k}: {v}\n"

    if context.get("connected_entities"):
        md += f"\n### 关联实体 ({len(context['connected_entities'])})\n"
        for ent in context["connected_entities"]:
            md += f"- **{ent.get('name', 'unknown')}** ({ent.get('type', '')}) `{ent.get('uri', '')}`\n"

    if context.get("paths"):
        md += f"\n### 关联关系 ({len(context['paths'])})\n"
        for path in context["paths"]:
            s = path.get("start_uri", "")
            e = path.get("end_uri", "")
            r = path.get("relationship", "")
            md += f"- `{s}` → *{r}* → `{e}`\n"

    return md


async def get_entity_paths_base(
    start_uri: str,
    end_uri: str,
    max_hops: int = 5,
) -> str:
    paths = await rag_mode.graph_manager.afind_entity_paths(start_uri, end_uri, max_hops)

    if not paths.get("nodes") or not paths.get("edges"):
        return f"## 路径查询\n\n未找到从 `{start_uri}` 到 `{end_uri}` 的路径（{max_hops}跳内）。"

    md = "## 路径查询结果\n\n"
    md += f"从 `{start_uri}` 到 `{end_uri}`\n\n"

    nodes_by_uri = {n["uri"]: n for n in paths["nodes"]}

    md += "### 路径节点\n"
    for i, edge in enumerate(paths["edges"]):
        s_name = nodes_by_uri.get(edge["start_uri"], {}).get("name", edge["start_uri"])
        o_name = nodes_by_uri.get(edge["end_uri"], {}).get("name", edge["end_uri"])
        rel = edge.get("relationship", "related_to")
        md += f"{i + 1}. **{s_name}** → *{rel}* → **{o_name}**\n"

    return md


async def get_document_context_base(
    document_index: int,
    chunk_index: int | None = None,
    before: int = 1,
    after: int = 1,
) -> str:
    context = await rag_mode.aget_document_context(
        document_index=document_index,
        chunk_index=chunk_index,
        before=before,
        after=after,
    )

    total = context["total_chunks"]
    chunks = context["chunks"]
    doc_id = context["document_index"]

    md = f"## 文档上下文 (ID: {doc_id})\n\n"
    md += f"总块数: {total} | 获取: {len(chunks)} 块\n\n"

    if chunk_index is not None:
        md += f"当前块索引: {chunk_index} (前后各 {before}/{after} 块)\n\n"

    for chunk in chunks:
        ci = chunk["chunk_index"]
        cid = chunk["id"]
        content = chunk["content"]
        preview = content[:500] + "..." if len(content) > 500 else content
        md += f"### 分块 {ci}\n"
        md += f"- ID: `{cid}`\n"
        md += f"- 内容:\n```\n{preview}\n```\n\n"

    if total > len(chunks):
        md += "> 提示: 设置 `chunk_index` 和 `before`/`after` 参数查看更多分块。"
        md += f"\n> 使用 `get_document_entities` 工具通过 `document_index={doc_id}` 查询该文档的相关图实体。"

    return md


async def get_document_entities_base(document_index: int) -> str:
    result = await rag_mode.aget_document_entities(document_index=document_index)

    entities = result["entities"]
    doc_id = result["document_index"]

    md = f"## 文档实体 (document_index: {doc_id})\n\n"

    if not entities:
        md += "未找到与该文档关联的图实体。"
        return md

    data = []
    for ent in entities:
        data.append({
            "名称": ent["name"],
            "类型": ent["entity_type"],
            "URI": ent["uri"],
        })

    dff = pd.DataFrame(data)
    md += dff.to_markdown(index=False)
    md += "\n\n> 使用 `traverse_graph` 工具通过实体URI深入探索图谱。"
    md += "\n> 使用 `get_entity_info` 查看特定实体的详细信息。"

    return md


@cache
def _get_tavily() -> AsyncTavilyClient:
    return AsyncTavilyClient()


async def search_web_base(
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    include_image: bool = False,
) -> dict:
    try:
        return await _get_tavily().search(
            query,
            max_results=max_results,
            include_domains=include_domains,  # type: ignore
            exclude_domains=exclude_domains,  # type: ignore
            include_image=include_image,
        )
    except Exception as e:
        return {"error": str(e), "results": []}


async def extract_web_base(
    urls: list[str],
    query: str | None = None,
    include_image: bool = False,
) -> dict:
    try:
        return await _get_tavily().extract(
            urls,
            include_images=include_image,
            query=query,  # type: ignore
        )
    except Exception as e:
        return {"error": str(e), "results": []}


async def crawl_web_base(
    url: str,
    max_depth: int = 1,
    max_pages: int = 10,
) -> dict:
    try:
        return await _get_tavily().crawl(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
        )
    except Exception as e:
        return {"error": str(e), "results": []}


async def fetch_web_base(url: str, format: str = "text") -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        html_content = response.text
    if format == "html":
        return html_content
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator="\n")


async def python_repl_base(code: str) -> str:
    monty = Monty(code=code)
    out = []

    def print_callback(stream: Literal["stdout"], content: str) -> None:
        if stream == "stdout":
            out.append(content)

    result = await monty.run_async(print_callback=print_callback)
    output = "表达式结果: " + pretty_repr(result)
    if out:
        output += "\n输出:\n" + "".join(out)
    return output
