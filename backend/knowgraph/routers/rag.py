from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from knowgraph.database.rag import RAGConfig
from knowgraph.database.ragmode import RAGMode
from knowgraph.utils.file import FileStream

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


class FileUploadResponse(BaseModel):
    success: bool
    status: str
    file_ids: list[UUID]


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


@router.post("/{rag_id}/files", response_model=FileUploadResponse)
async def api_upload_files(rag_id: UUID, files: list[UploadFile]) -> FileUploadResponse:
    try:
        file_streams = [await FileStream.afrom_request(f) for f in files]
        rag_mode = RAGMode()
        file_ids = await rag_mode.aadd_embedding_documents(rag_id, file_streams)
        return FileUploadResponse(success=True, status="文件上传成功", file_ids=file_ids)
    except Exception as e:
        return FileUploadResponse(success=False, status=f"文件上传失败: {e!s}", file_ids=[])


@router.delete("/{rag_id}/files")
async def api_delete_files(rag_id: UUID, file_ids: list[UUID]) -> dict[str, Any]:
    try:
        rag_mode = RAGMode()
        await rag_mode.adelete_embedding_documents(rag_id, file_ids)
        return {"success": True, "status": "删除文件成功"}
    except Exception as e:
        return {"success": False, "status": f"删除文件失败: {e!s}"}


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


@router.post("/reindex")
async def api_reindex() -> dict[str, Any]:
    try:
        rag_mode = RAGMode()
        await rag_mode.areindex()
        return {"success": True, "status": "重建索引成功"}
    except Exception as e:
        return {"success": False, "status": f"重建索引失败: {e!s}"}
