import pathlib

from fastapi import APIRouter, UploadFile

from knowgraph.database.document import DocumentStore
from knowgraph.database.ragmode import RAGMode

from .schema import DocumentUploadResponse, FileIngestResponse, SearchRequest, SearchResponse

router = APIRouter()


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


# ── Document Ingestion ──


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def api_upload_document(file: UploadFile) -> DocumentUploadResponse:
    try:
        import os
        import tempfile

        suffix = os.path.splitext(file.filename or "")[1]  # noqa: PTH122
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        doc_store = DocumentStore()
        doc_ids = await doc_store.aload_from_document(tmp_path)
        pathlib.Path(tmp_path).unlink()  # noqa: ASYNC240
        return DocumentUploadResponse(
            success=True,
            status="文档上传成功",
            doc_ids=[str(d) for d in doc_ids],
        )
    except Exception as e:
        return DocumentUploadResponse(success=False, status=f"文档上传失败: {e!s}", doc_ids=[])


@router.post("/documents/load-csv", response_model=FileIngestResponse)
async def api_load_csv(csv_path: str) -> FileIngestResponse:
    try:
        doc_store = DocumentStore()
        file_ids = await doc_store.aload_from_csv(csv_path)
        return FileIngestResponse(
            success=True,
            status="CSV 文档加载成功",
            file_ids=[str(f) for f in file_ids],
        )
    except Exception as e:
        return FileIngestResponse(success=False, status=f"CSV 文档加载失败: {e!s}", file_ids=[])


@router.post("/documents/ingest-artifacts", response_model=FileIngestResponse)
async def api_ingest_artifacts(museum: str | None = None, limit: int | None = None) -> FileIngestResponse:
    try:
        doc_store = DocumentStore()
        file_ids = await doc_store.alingest_artifacts(museum=museum, limit=limit)
        return FileIngestResponse(
            success=True,
            status="文物数据提取成功",
            file_ids=[str(f) for f in file_ids],
        )
    except Exception as e:
        return FileIngestResponse(success=False, status=f"文物数据提取失败: {e!s}", file_ids=[])
