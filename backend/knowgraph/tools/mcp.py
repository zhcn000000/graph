from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from knowgraph.tools.base import (
    crawl_web_base,
    extract_web_base,
    fetch_web_base,
    get_document_context_base,
    get_document_entities_base,
    get_entity_info_base,
    get_entity_paths_base,
    python_repl_base,
    search_documents_base,
    search_web_base,
    traverse_graph_base,
)

mcp = FastMCP("knowgraph")


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
    try:
        return await search_documents_base(
            queries=queries,
            regex=regex,
            file_ids=file_ids,
            offset=offset,
            use_graph=use_graph,
        )
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
        return await traverse_graph_base(
            entity_uris=entity_uris,
            max_hops=max_hops,
            direction=direction,
        )
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
        return await get_entity_info_base(uri=uri)
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
        return await get_entity_paths_base(
            start_uri=start_uri,
            end_uri=end_uri,
            max_hops=max_hops,
        )
    except Exception as e:
        raise ToolError(f"路径查询失败: {e!s}") from e


@mcp.tool(
    name="get_document_context",
    description="""
获取指定文档的完整分块上下文，支持翻页查看文档的前后分块。
当一个文档在搜索中被截断时，使用此工具获取该文档的相邻分块以获得更完整的上下文。
返回结果包含 document_index，可用于后续查询相关图实体。
""",
)
async def get_document_context(
    document_index: Annotated[int, Field(description="文档ID,来自搜索结果中的document_index字段")],
    chunk_index: Annotated[
        int | None,
        Field(description="当前所在的分块索引,用于获取前后相邻分块。不传则返回全部"),
    ] = None,
    before: Annotated[int, Field(description="获取当前分块之前的多少个分块")] = 1,
    after: Annotated[int, Field(description="获取当前分块之后的多少个分块")] = 1,
) -> Annotated[str, Field(description="返回markdown格式的文档分块上下文")]:
    try:
        return await get_document_context_base(
            document_index=document_index,
            chunk_index=chunk_index,
            before=before,
            after=after,
        )
    except Exception as e:
        raise ToolError(f"获取文档上下文失败: {e!s}") from e


@mcp.tool(
    name="get_document_entities",
    description="""
获取指定文档关联的所有知识图谱实体。
通过搜索结果中的 document_index 查询该文档中的图实体（如人物、地点、事件等）。
可用于深入了解某个文档中涉及的知识实体及其关系。
""",
)
async def get_document_entities(
    document_index: Annotated[int, Field(description="文档ID,来自搜索结果中的document_index字段")],
) -> Annotated[str, Field(description="返回markdown格式的实体列表")]:
    try:
        return await get_document_entities_base(document_index=document_index)
    except Exception as e:
        raise ToolError(f"获取文档实体失败: {e!s}") from e


@mcp.tool(
    name="python_repl",
    description="这是一个可以执行Python代码的工具，输入Python代码并返回最后一条表达式的结果和控制台输出。"
    "为了沙盒的安全性，以及沙盒的局限性，该工具不支持任何需要使用import导入的库，除了sys, typing, asyncio",
)
async def python_repl(
    code: Annotated[str, Field(description="要执行的Python代码")],
) -> Annotated[str, Field(description="返回最后一行表达式的结果和控制台输出")]:
    try:
        return await python_repl_base(code=code)
    except Exception as e:
        raise ToolError(f"执行Python代码时发生错误: {e}") from e


@mcp.tool(
    name="search_web",
    description="网络搜索工具，输入搜索关键词，返回搜索结果摘要。",
)
async def search_web(
    query: Annotated[str, Field(description="搜索关键词")],
    max_results: Annotated[int, Field(description="返回的最大搜索结果数量")] = 5,
    include_domains: Annotated[list[str] | None, Field(description="要包含的域名列表")] = None,
    exclude_domains: Annotated[list[str] | None, Field(description="要排除的域名列表")] = None,
) -> dict[str, Any]:
    try:
        return await search_web_base(
            query=query,
            max_results=max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
    except Exception as e:
        raise ToolError(f"网络搜索失败: {e!s}") from e


@mcp.tool(
    name="extract_web",
    description="提取网页内容工具，输入网页URL列表，返回网页的主要内容摘要。",
)
async def extract_web(
    urls: Annotated[list[str], Field(description="要提取内容的网页URL列表")],
    query: Annotated[str | None, Field(description="可选的查询关键词，用于指导内容提取")] = None,
) -> dict[str, Any]:
    try:
        return await extract_web_base(urls=urls, query=query)
    except Exception as e:
        raise ToolError(f"网页内容提取失败: {e!s}") from e


@mcp.tool(
    name="crawl_web",
    description="网页爬取工具，输入网页URL，递归爬取并返回网页文本内容。",
)
async def crawl_web(
    url: Annotated[str, Field(description="要爬取内容的网页URL")],
    max_depth: Annotated[int, Field(description="爬取的最大深度")] = 1,
    max_pages: Annotated[int, Field(description="爬取的最大页面数量")] = 10,
) -> dict[str, Any]:
    try:
        return await crawl_web_base(url=url, max_depth=max_depth, max_pages=max_pages)
    except Exception as e:
        raise ToolError(f"网页爬取失败: {e!s}") from e


@mcp.tool(
    name="fetch_web",
    description="获取网页原始内容工具，输入网页URL，返回网页的文本内容。",
)
async def fetch_web(
    url: Annotated[str, Field(description="要获取内容的网页URL")],
    format: Annotated[Literal["text", "html"], Field(description="内容格式，支持html和text两种格式")] = "text",
) -> str:
    try:
        return await fetch_web_base(url=url, format=format)
    except Exception as e:
        raise ToolError(f"网页获取失败: {e!s}") from e
