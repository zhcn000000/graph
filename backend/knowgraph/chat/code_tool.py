import logging
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import FunctionToolset, ModelRetry, RunContext, ToolDefinition
from pydantic_monty import Monty
from rich.pretty import pretty_repr

from .struct import ModelDeps

IMAGE_NAME = "nw.lonwell.cn:29911/default/ragbuild/code_sandbox:latest"

PODMAN_CLIENT = None

logger = logging.getLogger(__name__)


toolset: FunctionToolset[ModelDeps] = FunctionToolset()


async def prepare_code_tools(ctx: RunContext[ModelDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    """根据上下文动态添加代码执行相关工具."""
    if "code_toolkit" in ctx.deps.select_toolset:
        return tool_def
    return None


@toolset.tool(
    prepare=prepare_code_tools,
    name="python_repl",
    description="这是一个可以执行Python代码的工具，输入Python代码并返回最后一条表达式的结果和控制台输出。"
    "为了沙盒的安全性，以及沙盒的局限性，该工具不支持任何需要使用import导入的库，除了sys, typing, asyncio",
)
async def python_repl(
    ctx: RunContext[ModelDeps],
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
        raise ModelRetry(f"执行Python代码时发生错误: {e}") from e
    output = "表达式结果: " + pretty_repr(result)
    if out:
        output += "\n输出:\n" + "".join(out)
    return output
