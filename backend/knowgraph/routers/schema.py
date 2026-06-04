from typing import Any
from uuid import UUID

from pydantic import BaseModel

# ── Base Response ──


class StatusResponse(BaseModel):
    success: bool = True
    status: str = "Donw"


# ── Auth / User ──


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCredentialsRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: UUID
    username: str


class UserListResponse(BaseModel):
    users: list[UserResponse]


class UpdateUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None


# ── Graph ──


class GraphEntityRequest(BaseModel):
    label: str
    properties: dict[str, Any]


class GraphEdgeRequest(BaseModel):
    start_uri: str
    end_uri: str
    relationship_type: str
    properties: dict[str, Any] | None = None


class GraphContextRequest(BaseModel):
    entity_uri: str
    max_hops: int = 2
    direction: str = "both"


class PathQueryRequest(BaseModel):
    start_uri: str
    end_uri: str
    max_hops: int = 5


class TraverseMultiRequest(BaseModel):
    uris: list[str]
    max_hops: int = 3
    direction: str = "both"


class GraphOperationResponse(StatusResponse):
    data: dict[str, Any] | None = None


# ── Search ──


class SearchRequest(BaseModel):
    queries: list[str]
    regex: str | None = None
    artifact_ids: list[UUID] | None = None
    use_graph: bool = True
    max_hops: int = 2
    graph_weight: float = 0.3
    vector_weight: float = 0.4
    bm25_weight: float = 0.3
    offset: int = 0
    k: int = 4


class SearchResponse(StatusResponse):
    results: list[dict[str, Any]]
    graph_entities: list[dict[str, Any]] = []


# ── Document Ingestion ──


class DocumentUploadResponse(StatusResponse):
    doc_ids: list[str]


class FileIngestResponse(StatusResponse):
    doc_ids: list[str]


class CsvLoadResponse(StatusResponse):
    artifact_count: int


# ── Chat ──


class ToolItem(BaseModel):
    name: str
    id: str
    args: dict[str, Any]


class FileItem(BaseModel):
    type: str
    name: str
    url: str


class MessageItem(BaseModel):
    role: str
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolItem] | None = None
    files: list[FileItem] | None = None
    success: bool = True


class SystemMessageItem(BaseModel):
    role: str
    content: str
    success: bool = True


class UserMessageItem(BaseModel):
    role: str
    content: str | None = None
    files: list[FileItem] | None = None
    success: bool = True


class ToolMessageItem(BaseModel):
    role: str
    tool_call_id: str
    name: str
    content: str | None = None
    files: list[FileItem] | None = None
    success: bool = True


class AssistantMessageItem(BaseModel):
    role: str
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolItem] | None = None
    files: list[FileItem] | None = None
    success: bool = True


class ChatRequest(BaseModel):
    text: str
    files: list[str | dict] = []
    model: str | None = None
    thinking: bool = True
    select_toolset: set[str] = {"rag_toolkit", "code_toolkit", "web_toolkit"}


class ChatTitleRequest(BaseModel):
    text: str


class RenameRequest(BaseModel):
    name: str


class ChatTitleResponse(StatusResponse):
    title: str


class TranscriptionResponse(StatusResponse):
    text: str


class SessionCreateResponse(StatusResponse):
    session_id: UUID
    name: str


class SessionItem(BaseModel):
    session_id: UUID
    name: str


class SessionListResponse(StatusResponse):
    sessions: list[SessionItem]


class HistoryResponse(StatusResponse):
    messages: list[MessageItem]
