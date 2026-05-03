from datetime import UTC, datetime

from pydantic_ai import Agent, RunContext

from knowgraph.utils.templete import FIRST_INPUT_TEMPLATE

from .chat_model import get_model
from .struct import ModelDeps
from .tools import toolset as rag_toolset

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

    prompt = f"""
    你是模型：{model_name}
    当前时间是(UTC)：{time}"""
    return prompt
