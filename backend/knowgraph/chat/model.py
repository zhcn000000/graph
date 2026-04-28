from datetime import UTC, datetime

from pydantic_ai import Agent, RunContext
from simplerag.utils.templete import FIRST_INPUT_TEMPLATE, RAG_TEMPLATE

from .chat_model import get_model
from .rag_tool import toolset as rag_toolset
from .struct import ModelDeps

agent: Agent[ModelDeps, str] = Agent(
    model=get_model(),
    deps_type=ModelDeps,
    toolsets=[rag_toolset],
    instructions=FIRST_INPUT_TEMPLATE,
    output_retries=5,
)


@agent.instructions
async def metadata_prompt(ctx: RunContext[ModelDeps]):
    time = datetime.now(UTC).isoformat()
    model_name = ctx.model.model_name
    toolsets = ctx.deps.select_toolset

    prompt = f"""
    你是模型：{model_name}
    当前时间是(UTC)：{time}"""
    if toolsets:
        prompt += f"""\n当前选择的工具是：{"，".join(toolsets)}"""
    return prompt


@agent.instructions
async def rag_prompt(ctx: RunContext[ModelDeps]):
    if "rag_toolkit" in ctx.deps.select_toolset:
        return RAG_TEMPLATE
    return None
