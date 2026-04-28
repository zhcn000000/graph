from typing import Annotated

import pandas as pd
from pydantic import Field
from pydantic_ai import FunctionToolset, ModelRetry, RunContext, ToolDefinition

from knowgraph.database.rag import RAGConfig
from knowgraph.database.ragmode import RAGMode
from knowgraph.database.source import SourceStore

from .struct import ModelDeps

config = RAGConfig()

toolset: FunctionToolset[ModelDeps] = FunctionToolset()


async def prepare_rag_tools(ctx: RunContext[ModelDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    if "rag_toolkit" in ctx.deps.select_toolset:
        return tool_def
    return None


@toolset.tool(prepare=prepare_rag_tools, name="list_rag", description="列出所有已配置的知识库名称,列出名称和描述信息")
async def list_rag(
    ctx: RunContext[ModelDeps],
) -> Annotated[str, Field(description="返回markdown格式的字符串，包含知识库列表的表格")]:
    try:
        rags = await RAGConfig().alists()

        if not rags:
            return "## 知识库列表\n\n当前没有配置的知识库。"

        data = [{"知识库名称": rag["name"], "描述": rag["description"]} for rag in rags.values()]
        dff = pd.DataFrame(data)
        md = "## 知识库列表\n\n"
        md += dff.to_markdown(index=False)
        return md
    except AssertionError as e:
        raise ModelRetry("用户提供信息缺失，请提示用户提供额外信息，错误信息：" + str(e)) from e
    except Exception as e:
        msg = f"获取知识库列表失败，错误信息：{e!s}"
        raise ModelRetry(msg) from e


@toolset.tool(
    prepare=prepare_rag_tools,
    name="info_rag",
    description="获取指定知识库的详细信息，包括描述和包含文件列表",
)
async def info_rag(
    ctx: RunContext[ModelDeps],
    rag_name: Annotated[str, Field(description="知识库的名称")],
) -> Annotated[str, Field(description="返回markdown格式的字符串，包含知识库的详细信息")]:
    try:
        rag_id = (await config.aget_id_by_names([rag_name]))[0]

        info = await config.aget(rag_id=rag_id)
        if info is None:
            raise ValueError(f"未找到ID为 {rag_id} 的知识库信息。")
        file_ids = info.get("file_ids", [])
        if file_ids:
            file_names = await SourceStore().aget_name_by_ids(file_ids)
        else:
            file_names = []

        md = "## 知识库详细信息\n\n"
        md += f"**知识库名称**: `{info['name']}`\n\n"
        md += f"**描述**: {info['description']}\n\n"
        md += f"**包含文件数**: {len(file_names)}\n\n"

        if info["file_ids"]:
            md += "**文件列表**:\n\n"
            for i, filename in enumerate(file_names, 1):
                md += f"{i}. {filename}\n"
        else:
            md += "**文件列表**: 无\n"

        return md
    except AssertionError as e:
        raise ModelRetry("用户提供信息缺失，请提示用户提供额外信息，错误信息：" + str(e)) from e
    except Exception as e:
        msg = f'未找到名称为 "{rag_name}" 的知识库，请确认名称是否正确，错误信息：{e!s}'
        raise ModelRetry(msg) from e


@toolset.tool(
    prepare=prepare_rag_tools,
    name="search_rag",
    description="""
    根据询问(query)语义搜索知识库，可以先通过find_rag工具找到与问题相关的知识库名称,
    你可以根据用户问题的复杂程度，从不同角度输入1-3个查询语句来搜索知识库，如果用户问题比较简单，可以只输入一个查询语句，
    如果用户问题十分复杂，也可以从不同角度提出多于3个查询，但建议不超过5个查询语句，以免影响搜索效果。
    如果用户有需求，如包含关键词，不包含关键词等，可以提供正则表达式过滤条件来进一步筛选搜索结果，
    但是如果没有需求，则最好不要使用该参数以免影响搜索速度。
    如果用户指定了特定文件或文件列表，可以通过files参数限制搜索范围，只在指定的文件中搜索。
    调用此工具会返回与查询相关的文档内容列表.
    该方法返回markdown格式的字符串，包含搜索结果的表格。
    """,
    retries=3,
)
async def search_rag(
    ctx: RunContext[ModelDeps],
    rag_name: Annotated[str, Field(description="知识库的名称")],
    queries: Annotated[list[str], Field(description="搜索知识库的查询内容,可以是多个查询")],
    regex: Annotated[str | None, Field(description="可选的正则表达式过滤条件")] = None,
    files: Annotated[list[str] | None, Field(description="可选的文件名列表过滤条件")] = None,
) -> Annotated[str, Field(description="返回markdown格式的字符串，包含搜索结果的表格")]:
    from knowgraph.database.source import SourceStore

    try:
        rag_id = (await config.aget_id_by_names([rag_name]))[0]

        file_ids = None
        if files:
            try:
                source_store = SourceStore()
                file_ids = await source_store.aget_id_by_names(files)
            except ValueError as e:
                msg = f"部分文件名不存在: {', '.join(files)}，请确认文件名是否正确，错误信息：{e!s}"
                raise ModelRetry(msg) from e

        documents = await RAGMode().aquery_documents(rag_id=rag_id, queries=queries, regex=regex, file_ids=file_ids)

        if not documents:
            return f'## 搜索结果\n\n在知识库 `{rag_name}` 中未找到与查询 "{queries}" 相关的文档。'

        data = [
            {"文档编号": i, "文档内容": doc[0], "文件名": doc[1], "相关性": f"{(doc[2] ** 0.4 * 100):.2f}%"}
            for i, doc in enumerate(documents)
        ]
        dff = pd.DataFrame(data)
        md = f"## 搜索结果\n\n**知识库名称**: `{rag_name}`\n\n**查询**: {queries}\n\n"
        if files:
            md += f"**限制文件**: {', '.join(files)}\n\n"
        md += dff.to_markdown(index=False)

        return md
    except AssertionError as e:
        raise ModelRetry("用户提供信息缺失，请提示用户提供额外信息，错误信息：" + str(e)) from e
    except Exception as e:
        msg = f'未找到名称为 "{rag_name}" 的知识库，请确认名称是否正确，错误信息：{e!s}'
        raise ModelRetry(msg) from e
