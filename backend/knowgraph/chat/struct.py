from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class ToolEnum(StrEnum):
    rag_toolkit = "rag_toolkit"


class ModelState(BaseModel):
    select_toolset: Annotated[list[ToolEnum], Field(default_factory=list)]


class ModelDeps(BaseModel):
    select_toolset: Annotated[list[ToolEnum], Field(default_factory=list)]
    max_result_retries: int = 3
