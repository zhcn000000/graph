from typing import Annotated, Literal

import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from pydantic_monty import Monty
from rich.pretty import pretty_repr

from knowgraph.database import RAGMode

mcp = FastMCP("knowgraph")
rag_mode = RAGMode()


@mcp.tool(
    name="search_documents",
    description="""
根据查询语义搜索文档库，返回分页的文档列表。
你可以从不同角度输入1-5个查询语句来提高搜索覆盖度。
如果用户指定了特定文件，可以通过`file_ids`限制搜索范围。
如果用户指定了包含/排除关键词，可以提供`regex`正则表达式过滤。
返回结果包含文档内容和相关实体，支持翻页查看更多结果。
""",
)
async def search_documents(
    queries: Annotated[list[str], Field(description="搜索查询语句,1-5个")],
    regex: Annotated[str | None, Field(description="可选的正则表达式过滤条件")] = None,
    file_ids: Annotated[list[str] | None, Field(description="可选的源文件ID列表过滤条件")] = None,
    offset: Annotated[int, Field(description="分页偏移量,默认0")] = 0,
    use_graph: Annotated[bool, Field(description="是否启用图谱扩展搜索")] = True,
) -> Annotated[str, Field(description="返回markdown格式的搜索结果表格,包含实体信息和分页提示")]:
    from uuid import UUID

    try:
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
            score = doc.query_score if doc.query_score is not None else float("nan")
            source = doc.name or "unknown"
            preview = doc.content[:300] + "..." if len(doc.content) > 300 else doc.content
            data.append({
                "#": offset + i + 1,
                "来源": source,
                "内容预览": preview,
                "相关性%": f"{min(score, 1.0) * 100:.1f}",
            })

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
        md += "\n> 使用 `traverse_graph` 工具沿实体URI深入探索图谱。"

        return md
    except Exception as e:
        raise ToolError(f"搜索失败: {e!s}") from e


@mcp.tool(
    name="traverse_graph",
    description="""
沿知识图谱中的实体URI向外遍历，获取关联实体及其相关文档。
可用于深入了解搜索结果中发现的实体，扩展知识上下文。
支持控制遍历方向和跳数。
""",
)
async def traverse_graph(
    entity_uris: Annotated[list[str], Field(description="起始实体URI列表")],
    max_hops: Annotated[int, Field(description="最大跳数,默认2")] = 2,
    direction: Annotated[str, Field(description="遍历方向: outbound/inbound/both")] = "both",
) -> Annotated[str, Field(description="返回markdown格式的图谱遍历结果")]:
    try:
        graph = await rag_mode.graph_manager.atraverse_multi(entity_uris, max_hops=max_hops, direction=direction)

        if graph.number_of_nodes() == 0:
            return "## 图谱遍历结果\n\n未找到相关实体或关系。"

        nodes_data = []
        for node_key, data in graph.nodes(data=True):
            uri = data.get("uri", str(node_key))
            name = data.get("name", uri)
            etype = data.get("entity_type", "")
            nodes_data.append({
                "名称": name,
                "类型": etype,
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
    except Exception as e:
        raise ToolError(f"图谱遍历失败: {e!s}") from e


@mcp.tool(
    name="get_entity_info",
    description="""
获取知识图谱中指定实体的详细信息，包括属性、关联关系等。
用于深入了解某个特定实体。
""",
)
async def get_entity_info(
    uri: Annotated[str, Field(description="实体URI")],
) -> Annotated[str, Field(description="返回markdown格式的实体详情")]:
    try:
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

        extra = {
            k: v for k, v in vertex.items() if k not in {"id", "label", "uri", "name", "entity_type", "description"}
        }
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
    except Exception as e:
        raise ToolError(f"获取实体信息失败: {e!s}") from e


@mcp.tool(
    name="get_entity_paths",
    description="""
查询两个实体之间的最短路径。
用于理解两个实体之间的关联方式。
""",
)
async def get_entity_paths(
    start_uri: Annotated[str, Field(description="起始实体URI")],
    end_uri: Annotated[str, Field(description="目标实体URI")],
    max_hops: Annotated[int, Field(description="最大跳数,默认5")] = 5,
) -> Annotated[str, Field(description="返回markdown格式的路径查询结果")]:
    try:
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
    except Exception as e:
        raise ToolError(f"路径查询失败: {e!s}") from e


@mcp.tool(
    name="python_repl",
    description="这是一个可以执行Python代码的工具，输入Python代码并返回最后一条表达式的结果和控制台输出。"
    "为了沙盒的安全性，以及沙盒的局限性，该工具不支持任何需要使用import导入的库，除了sys, typing, asyncio",
)
async def python_repl(
    code: Annotated[str, Field(description="要执行的Python代码")],
) -> Annotated[str, Field(description="返回最后一行表达式的结果和控制台输出")]:
    monty = Monty(code=code)
    out = []

    def print_callback(stream: Literal["stdout"], content: str) -> None:
        if stream == "stdout":
            out.append(content)

    try:
        result = await monty.run_async(print_callback=print_callback)
    except Exception as e:
        raise ToolError(f"执行Python代码时发生错误: {e}") from e
    output = "表达式结果: " + pretty_repr(result)
    if out:
        output += "\n输出:\n" + "".join(out)
    return output
