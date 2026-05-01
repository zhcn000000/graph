from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from knowgraph.database import RAGMode
from knowgraph.database.graph import AgeGraphManager
from knowgraph.database.rag import RAGConfig

router = APIRouter()


class RAGCreateRequest(BaseModel):
    name: str
    description: str = ""


class RAGUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class RAGInfoResponse(BaseModel):
    success: bool
    status: str
    rag: dict[str, Any] | None = None


class RAGListResponse(BaseModel):
    success: bool
    status: str
    rags: dict[str, Any]


class RAGSearchRequest(BaseModel):
    queries: list[str]
    regex: str | None = None
    file_ids: list[UUID] | None = None


class RAGSearchResponse(BaseModel):
    success: bool
    status: str
    results: list[dict[str, Any]]


class SourceCreateRequest(BaseModel):
    name: str
    content: str
    link: str | None = None
    source_hash: str | None = None


class SourceCreateResponse(BaseModel):
    success: bool
    status: str
    source_id: UUID | None = None


class SourceDeleteResponse(BaseModel):
    success: bool
    status: str
    removed_ids: list[UUID]


@router.post("/", response_model=RAGInfoResponse)
async def api_create_rag(request: RAGCreateRequest) -> RAGInfoResponse:
    try:
        config = RAGConfig()
        await config.ainsert(
            name=request.name,
            description=request.description,
        )
        return RAGInfoResponse(success=True, status="知识库创建成功", rag=None)
    except Exception as e:
        return RAGInfoResponse(success=False, status=f"创建知识库失败: {e!s}", rag=None)


@router.get("/list", response_model=RAGListResponse)
async def api_list_rags() -> RAGListResponse:
    try:
        config = RAGConfig()
        rags = await config.alists()
        return RAGListResponse(success=True, status="获取知识库列表成功", rags=rags)
    except Exception as e:
        return RAGListResponse(success=False, status=f"获取知识库列表失败: {e!s}", rags={})


@router.get("/{rag_id}", response_model=RAGInfoResponse)
async def api_get_rag(rag_id: UUID) -> RAGInfoResponse:
    try:
        config = RAGConfig()
        rag = await config.aget(rag_id)
        if rag is None:
            return RAGInfoResponse(success=False, status="知识库不存在", rag=None)
        rag_dict = cast("dict[str, Any]", rag)
        return RAGInfoResponse(success=True, status="获取知识库信息成功", rag=rag_dict)
    except Exception as e:
        return RAGInfoResponse(success=False, status=f"获取知识库信息失败: {e!s}", rag=None)


@router.patch("/{rag_id}", response_model=RAGInfoResponse)
async def api_update_rag(rag_id: UUID, request: RAGUpdateRequest) -> RAGInfoResponse:
    try:
        config = RAGConfig()
        await config.aupdate(rag_id=rag_id, name=request.name, description=request.description)
        rag = await config.aget(rag_id)
        return RAGInfoResponse(success=True, status="更新知识库成功", rag=cast("dict[str, Any]", rag) if rag else None)
    except Exception as e:
        return RAGInfoResponse(success=False, status=f"更新知识库失败: {e!s}", rag=None)


@router.delete("/{rag_id}")
async def api_delete_rag(rag_id: UUID) -> dict[str, Any]:
    try:
        config = RAGConfig()
        await config.adelete(rag_id)
        return {"success": True, "status": "删除知识库成功"}
    except Exception as e:
        return {"success": False, "status": f"删除知识库失败: {e!s}"}


@router.post("/{rag_id}/sources", response_model=SourceCreateResponse)
async def api_add_source(rag_id: UUID, request: SourceCreateRequest) -> SourceCreateResponse:
    try:
        rag_mode = RAGMode()
        source_id = await rag_mode.aadd_link_documents(
            rag_id=rag_id,
            name=request.name,
            content=request.content,
            link=request.link,
            source_hash=request.source_hash,
        )
        return SourceCreateResponse(success=True, status="来源添加成功", source_id=source_id)
    except Exception as e:
        return SourceCreateResponse(success=False, status=f"添加来源失败: {e!s}", source_id=None)


@router.delete("/{rag_id}/sources")
async def api_delete_sources(rag_id: UUID, file_ids: list[UUID]) -> SourceDeleteResponse:
    try:
        rag_mode = RAGMode()
        removed = await rag_mode.aremove_documents(rag_id, file_ids)
        return SourceDeleteResponse(success=True, status="删除来源成功", removed_ids=removed)
    except Exception as e:
        return SourceDeleteResponse(success=False, status=f"删除来源失败: {e!s}", removed_ids=[])


@router.post("/{rag_id}/search", response_model=RAGSearchResponse)
async def api_search_rag(rag_id: UUID, request: RAGSearchRequest) -> RAGSearchResponse:
    try:
        rag_mode = RAGMode()
        results = await rag_mode.aquery_documents(
            rag_id=rag_id,
            queries=request.queries,
            regex=request.regex,
            file_ids=request.file_ids,
        )
        result_dicts = [{"content": r.content, "source_name": r.source_name, "score": r.score} for r in results]
        return RAGSearchResponse(success=True, status="搜索成功", results=result_dicts)
    except Exception as e:
        return RAGSearchResponse(success=False, status=f"搜索失败: {e!s}", results=[])


class GraphEntityRequest(BaseModel):
    label: str
    properties: dict[str, Any]


class GraphEdgeRequest(BaseModel):
    start_uri: str
    end_uri: str
    relationship_type: str
    properties: dict[str, Any] | None = None


class GraphSearchRequest(BaseModel):
    queries: list[str]
    k: int = 4
    use_graph: bool = False
    max_hops: int = 3
    graph_weight: float = 0.3
    vector_weight: float = 0.4
    bm25_weight: float = 0.3


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


@router.post("/graph/create")
async def api_create_graph() -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        result = await rag_mode.graph_manager.acreate_graph()
        status = "图创建成功" if result else "图已存在"
        return GraphOperationResponse(success=True, status=status, data={"created": result})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"创建图失败: {e!s}")


@router.post("/graph/drop")
async def api_drop_graph() -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        result = await rag_mode.graph_manager.adrop_graph()
        status = "图删除成功" if result else "图不存在"
        return GraphOperationResponse(success=True, status=status, data={"dropped": result})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"删除图失败: {e!s}")


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
        return GraphOperationResponse(
            success=True,
            status="遍历成功",
            data=AgeGraphManager.digraph_to_json(g),
        )
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"遍历失败: {e!s}")


@router.get("/graph/paths/{start_uri}/{end_uri}", response_model=GraphOperationResponse)
async def api_find_paths(start_uri: str, end_uri: str, max_hops: int = 5) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        g = await rag_mode.graph_manager.afind_paths(start_uri, end_uri, max_hops)
        return GraphOperationResponse(success=True, status="路径查询成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"查询路径失败: {e!s}")


@router.post("/graph/search", response_model=GraphOperationResponse)
async def api_graph_search(request: GraphSearchRequest) -> GraphOperationResponse:
    try:
        rag_mode = RAGMode()
        docs, graph_entities = await rag_mode.ahyprid_search(
            queries=request.queries,
            k=request.k,
            use_graph=True,
            max_hops=request.max_hops,
            graph_weight=request.graph_weight,
            vector_weight=request.vector_weight,
            bm25_weight=request.bm25_weight,
        )
        result_dicts = [
            {
                "content": d.content,
                "source_name": d.source_name,
                "score": d.query_score if d.query_score is not None else float("nan"),
            }
            for d in docs
        ]
        graph_data = [
            {
                "uri": g.entity_uri,
                "name": g.entity_name,
                "type": g.entity_type,
                "score": g.score,
            }
            for g in graph_entities
        ]
        return GraphOperationResponse(
            success=True,
            status="图搜索成功",
            data={"results": result_dicts, "graph_entities": graph_data},
        )
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"图搜索失败: {e!s}")


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
