from fastapi import APIRouter

from knowgraph.database.graph import AgeGraphManager
from knowgraph.database.ragmode import RAGMode

from .schema import (
    GraphContextRequest,
    GraphEdgeRequest,
    GraphEntityRequest,
    GraphOperationResponse,
    PathQueryRequest,
    TraverseMultiRequest,
)

router = APIRouter()

graph_manager = AgeGraphManager()
# ── Graph Vertices ──


@router.post("/vertex", response_model=GraphOperationResponse)
async def api_create_vertex(request: GraphEntityRequest) -> GraphOperationResponse:
    try:
        vertex = await graph_manager.amupsert_vertex(request.label, request.properties)
        return GraphOperationResponse(success=True, status="节点创建成功", data={"vertex": vertex})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"创建节点失败: {e!s}")


@router.get("/vertex/{uri}", response_model=GraphOperationResponse)
async def api_get_vertex(uri: str, label: str | None = None) -> GraphOperationResponse:
    try:
        vertex = await graph_manager.aget_vertex(uri, label)
        return GraphOperationResponse(success=True, status="获取节点成功", data={"vertex": vertex})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"获取节点失败: {e!s}")


@router.put("/vertex/{uri}", response_model=GraphOperationResponse)
async def api_update_vertex(uri: str, request: GraphEntityRequest, label: str | None = None) -> GraphOperationResponse:
    try:
        vertex = await graph_manager.amupsert_vertex(
            label or request.label,
            {"uri": uri, **request.properties},
        )
        return GraphOperationResponse(success=True, status="节点更新成功", data={"vertex": vertex})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"更新节点失败: {e!s}")


@router.delete("/vertex/{uri}", response_model=GraphOperationResponse)
async def api_delete_vertex(uri: str, label: str | None = None) -> GraphOperationResponse:
    try:
        result = await graph_manager.adelete_vertex(uri, label)
        return GraphOperationResponse(success=True, status="节点删除成功", data={"deleted": result})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"删除节点失败: {e!s}")


# ── Graph Edges ──


@router.post("/edge", response_model=GraphOperationResponse)
async def api_create_edge(request: GraphEdgeRequest) -> GraphOperationResponse:
    try:
        edge = await graph_manager.amupsert_edge(
            request.start_uri,
            request.end_uri,
            request.relationship_type,
            request.properties,
        )
        return GraphOperationResponse(success=True, status="边创建成功", data={"edge": edge})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"创建边失败: {e!s}")


@router.get("/edge/{start_uri}/{end_uri}", response_model=GraphOperationResponse)
async def api_get_edge(start_uri: str, end_uri: str, relationship_type: str | None = None) -> GraphOperationResponse:
    try:
        edge = await graph_manager.aget_edge(start_uri, end_uri, relationship_type)
        return GraphOperationResponse(success=True, status="获取边成功", data={"edge": edge})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"获取边失败: {e!s}")


@router.delete("/edge/{start_uri}/{end_uri}/{relationship_type}", response_model=GraphOperationResponse)
async def api_delete_edge(start_uri: str, end_uri: str, relationship_type: str) -> GraphOperationResponse:
    try:
        result = await graph_manager.adelete_edge(start_uri, end_uri, relationship_type)
        return GraphOperationResponse(success=True, status="边删除成功", data={"deleted": result})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"删除边失败: {e!s}")


# ── Graph Traversal ──


@router.get("/neighbors/{uri}", response_model=GraphOperationResponse)
async def api_get_neighbors(uri: str, direction: str = "both", max_hops: int = 1) -> GraphOperationResponse:
    try:
        g = await graph_manager.atraverse(uri, max_hops=max_hops, direction=direction)
        return GraphOperationResponse(success=True, status="获取邻居成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"获取邻居失败: {e!s}")


@router.get("/traverse/{start_uri}", response_model=GraphOperationResponse)
async def api_traverse(start_uri: str, max_hops: int = 3, direction: str = "both") -> GraphOperationResponse:
    try:
        g = await graph_manager.atraverse(start_uri, max_hops, direction)
        return GraphOperationResponse(success=True, status="遍历成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"遍历失败: {e!s}")


@router.post("/traverse/multi", response_model=GraphOperationResponse)
async def api_traverse_multi(request: TraverseMultiRequest) -> GraphOperationResponse:
    try:
        g = await graph_manager.atraverse_multi(
            request.uris,
            max_hops=request.max_hops,
            direction=request.direction,
        )
        return GraphOperationResponse(success=True, status="批量遍历成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"批量遍历失败: {e!s}")


@router.get("/paths/{start_uri}/{end_uri}", response_model=GraphOperationResponse)
async def api_find_paths(start_uri: str, end_uri: str, max_hops: int = 5) -> GraphOperationResponse:
    try:
        g = await graph_manager.afind_paths(start_uri, end_uri, max_hops)
        return GraphOperationResponse(success=True, status="路径查询成功", data=AgeGraphManager.digraph_to_json(g))
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"查询路径失败: {e!s}")


@router.post("/context", response_model=GraphOperationResponse)
async def api_graph_context(request: GraphContextRequest) -> GraphOperationResponse:
    try:
        context = await graph_manager.aexpand_context(
            entity_uri=request.entity_uri,
            max_hops=request.max_hops,
            direction=request.direction,
        )
        return GraphOperationResponse(success=True, status="图上下文扩展成功", data=context)
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"图上下文扩展失败: {e!s}")


@router.post("/entity-paths", response_model=GraphOperationResponse)
async def api_entity_paths(request: PathQueryRequest) -> GraphOperationResponse:
    try:
        paths = await graph_manager.afind_entity_paths(request.start_uri, request.end_uri, request.max_hops)
        return GraphOperationResponse(success=True, status="实体路径查询成功", data={"paths": paths})
    except Exception as e:
        return GraphOperationResponse(success=False, status=f"查询实体路径失败: {e!s}")
