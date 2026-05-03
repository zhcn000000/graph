from pydantic import BaseModel, Field


class Document(BaseModel):
    content: str
    name: str | None = None
    link: str | None = None
    query_score: float | None = None
    metadata: dict = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)
