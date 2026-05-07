import pathlib
from typing import Any
from uuid import UUID

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from knowgraph.database import RAGMode
from knowgraph.database.graph import AgeGraphManager

router = APIRouter()


class SearchRequest(BaseModel):
    queries: list[str]
    regex: str | None = None
    file_ids: list[UUID] | None = None
    use_graph: bool = True
    max_hops: int = 2
    graph_weight: float = 0.3
    vector_weight: float = 0.4
    bm25_weight: float = 0.3
    offset: int = 0
    k: int = 4


class SearchResponse(BaseModel):
    success: bool
    status: str
    results: list[dict[str, Any]]
    graph_entities: list[dict[str, Any]] = []


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


class GraphOperationResponse(BaseModel):
    success: bool
    status: str
    data: dict[str, Any] | None = None


class TraverseMultiRequest(BaseModel):
    uris: list[str]
    max_hops: int = 3
    direction: str = "both"


# ── Search ──


@router.post("/search", response_model=SearchResponse)
async def api_search(request: SearchRequest) -> SearchResponse:
    try:
        rag_mode = RAGMode()
        docs, graph_entities = await rag_mode.ahyprid_search(
            queries=request.queries,
            k=request.k,
            regex=request.regex,
            file_ids=request.file_ids,
            use_graph=request.use_graph,
            max_hops=request.max_hops,
            graph_weight=request.graph_weight,
            vector_weight=request.vector_weight,
            bm25_weight=request.bm25_weight,
            offset=request.offset,
        )
        results = [
            {
                "content": d.content,
                "source_name": d.name,
                "score": d.query_score if d.query_score is not None else float("nan"),
            }
            for d in docs
        ]
        graph_data = [
            {"uri": g.entity_uri, "name": g.entity_name, "type": g.entity_type, "score": g.score}
            for g in graph_entities
        ]
        return SearchResponse(success=True, status="搜索成功", results=results, graph_entities=graph_data)
    except Exception as e:
        return SearchResponse(success=False, status=f"搜索失败: {e!s}", results=[])


# ── Graph Vertices ──


@router.post("/graph/vertex", response_model=GraphOperationResponse)
async def api_create_vertex(request: GraphEntityRequest) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        vertex = await rag_mode.graph_manager.amupsert_vertex(request.label, request.properties)
        return GraphOperationResponse(success=True, status="节点创建成功", data={"vertex": vertex})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"创建节点失败: {e!s}")


@router.get("/graph/vertex/{uri}", response_model=GraphOperationResponse)
async def api_get_vertex(uri: str, label: str | None = None) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        vertex = await rag_mode.graph_manager.aget_vertex(uri, label)
        return GraphOperationResponse(success=True, status="获取节点成功", data={"vertex": vertex})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"获取节点失败: {e!s}")


@router.put("/graph/vertex/{uri}", response_model=GraphOperationResponse)
async def api_update_vertex(uri: str, request: GraphEntityRequest, label: str | None = None) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        vertex = await rag_mode.graph_manager.amupsert_vertex(
            label or request.label,
            {"uri": uri, **request.properties},
        )
        return GraphOperationResponse(success=True, status="节点更新成功", data={"vertex": vertex})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"更新节点失败: {e!s}")


@router.delete("/graph/vertex/{uri}", response_model=GraphOperationResponse)
async def api_delete_vertex(uri: str, label: str | None = None) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        result = await rag_mode.graph_manager.adelete_vertex(uri, label)
        return GraphOperationResponse(success=True, status="节点删除成功", data={"deleted": result})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"删除节点失败: {e!s}")


# ── Graph Edges ──


@router.post("/graph/edge", response_model=GraphOperationResponse)
async def api_create_edge(request: GraphEdgeRequest) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        edge = await rag_mode.graph_manager.amupsert_edge(
            request.start_uri,
            request.end_uri,
            request.relationship_type,
            request.properties,
        )
        return GraphOperationResponse(success=True, status="边创建成功", data={"edge": edge})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"创建边失败: {e!s}")


@router.get("/graph/edge/{start_uri}/{end_uri}", response_model=GraphOperationResponse)
async def api_get_edge(start_uri: str, end_uri: str, relationship_type: str | None = None) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        edge = await rag_mode.graph_manager.aget_edge(start_uri, end_uri, relationship_type)
        return GraphOperationResponse(success=True, status="获取边成功", data={"edge": edge})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"获取边失败: {e!s}")


@router.delete("/graph/edge/{start_uri}/{end_uri}/{relationship_type}", response_model=GraphOperationResponse)
async def api_delete_edge(start_uri: str, end_uri: str, relationship_type: str) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        result = await rag_mode.graph_manager.adelete_edge(start_uri, end_uri, relationship_type)
        return GraphOperationResponse(success=True, status="边删除成功", data={"deleted": result})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"删除边失败: {e!s}")


# ── Graph Traversal ──


@router.get("/graph/neighbors/{uri}", response_model=GraphOperationResponse)
async def api_get_neighbors(uri: str, direction: str = "both", max_hops: int = 1) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        g = await rag_mode.graph_manager.atraverse(uri, max_hops=max_hops, direction=direction)
        return GraphOperationResponse(success=True, status="获取邻居成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"获取邻居失败: {e!s}")


@router.get("/graph/traverse/{start_uri}", response_model=GraphOperationResponse)
async def api_traverse(start_uri: str, max_hops: int = 3, direction: str = "both") -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        g = await rag_mode.graph_manager.atraverse(start_uri, max_hops, direction)
        return GraphOperationResponse(success=True, status="遍历成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"遍历失败: {e!s}")


@router.post("/graph/traverse/multi", response_model=GraphOperationResponse)
async def api_traverse_multi(request: TraverseMultiRequest) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        g = await rag_mode.graph_manager.atraverse_multi(
            request.uris,
            max_hops=request.max_hops,
            direction=request.direction,
        )
        return GraphOperationResponse(success=True, status="批量遍历成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"批量遍历失败: {e!s}")


@router.get("/graph/paths/{start_uri}/{end_uri}", response_model=GraphOperationResponse)
async def api_find_paths(start_uri: str, end_uri: str, max_hops: int = 5) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        g = await rag_mode.graph_manager.afind_paths(start_uri, end_uri, max_hops)
        return GraphOperationResponse(success=True, status="路径查询成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"查询路径失败: {e!s}")


@router.post("/graph/context", response_model=GraphOperationResponse)
async def api_graph_context(request: GraphContextRequest) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        context = await rag_mode.graph_manager.aexpand_context(
            entity_uri=request.entity_uri,
            max_hops=request.max_hops,
            direction=request.direction,
        )
        return GraphOperationResponse(success=True, status="图上下文扩展成功", data=context)
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"图上下文扩展失败: {e!s}")


@router.post("/graph/entity-paths", response_model=GraphOperationResponse)
async def api_entity_paths(request: PathQueryRequest) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        paths = await rag_mode.graph_manager.afind_entity_paths(request.start_uri, request.end_uri, request.max_hops)
        return GraphOperationResponse(success=True, status="实体路径查询成功", data={"paths": paths})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"查询实体路径失败: {e!s}")


# ── Document Ingestion ──


class DocumentUploadResponse(BaseModel):
    success: bool
    status: str
    doc_ids: list[str]


class CSVLoadResponse(BaseModel):
    success: bool
    status: str
    file_ids: list[str]


class ArtifactIngestResponse(BaseModel):
    success: bool
    status: str
    file_ids: list[str]


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def api_upload_document(file: UploadFile) -> DocumentUploadResponse:
    try:
        import os
        import tempfile

        suffix = os.path.splitext(file.filename or "")[1]  # noqa: PTH122
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        rag_mode = RAGMode()
        doc_ids = await rag_mode.aload_from_document(tmp_path)
        pathlib.Path(tmp_path).unlink()  # noqa: ASYNC240
        return DocumentUploadResponse(
            success=True,
            status="文档上传成功",
            doc_ids=[str(d) for d in doc_ids],
        )
    except Exception as e:
        return DocumentUploadResponse(success=False, status=f"文档上传失败: {e!s}", doc_ids=[])


@router.post("/documents/load-csv", response_model=CSVLoadResponse)
async def api_load_csv(csv_path: str) -> CSVLoadResponse:
    try:
        rag_mode = RAGMode()
        file_ids = await rag_mode.aload_from_csv(csv_path)
        return CSVLoadResponse(
            success=True,
            status="CSV 文档加载成功",
            file_ids=[str(f) for f in file_ids],
        )
    except Exception as e:
        return CSVLoadResponse(success=False, status=f"CSV 文档加载失败: {e!s}", file_ids=[])


@router.post("/documents/ingest-artifacts", response_model=ArtifactIngestResponse)
async def api_ingest_artifacts(museum: str | None = None, limit: int | None = None) -> ArtifactIngestResponse:
    try:
        rag_mode = RAGMode()
        file_ids = await rag_mode.alingest_artifacts(museum=museum, limit=limit)
        return ArtifactIngestResponse(
            success=True,
            status="文物数据提取成功",
            file_ids=[str(f) for f in file_ids],
        )
    except Exception as e:
        return ArtifactIngestResponse(success=False, status=f"文物数据提取失败: {e!s}", file_ids=[])
