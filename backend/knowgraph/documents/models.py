from pydantic import BaseModel, Field


class Document(BaseModel):
    content: str
    source_name: str | None = None
    source_hash: str | None = None
    query_score: float | None = None
    metadata: dict = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)
