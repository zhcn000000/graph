from datetime import UTC, datetime

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider

from knowgraph.utils.templete import FIRST_INPUT_TEMPLATE

from .struct import ModelDeps
from .tools import toolset as rag_toolset

agent: Agent[ModelDeps, str] = Agent(
    model=OpenAIChatModel(model_name="deepseek-v4-flash", provider=DeepSeekProvider()),
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
