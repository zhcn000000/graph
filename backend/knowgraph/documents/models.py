from functools import cache
from uuid import UUID

import spacy
from pydantic import BaseModel, Field

from knowgraph.graph.schema import ExtractedTriple


class Document(BaseModel):
    content: str
    name: str | None = None
    link: str | None = None
    query_score: float | None = None
    metadata: dict = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)
    triples: list[ExtractedTriple] = Field(default_factory=list)
    id: UUID | None = None
    file_id: UUID | None = None
    document_index: int | None = None
    chunk_index: int | None = None


@cache
def get_nlp():
    return spacy.load("zh_core_web_trf")
