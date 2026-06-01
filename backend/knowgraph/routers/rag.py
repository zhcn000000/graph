import logging
import os
import pathlib
import tempfile
from typing import Annotated

from fastapi import APIRouter, Body, UploadFile

from knowgraph.adapters import PhilaMuseumAdapter, PhilaMuseumRawAdapter
from knowgraph.database.artifact import ArtifactStore
from knowgraph.database.document import DocumentStore
from knowgraph.database.ragmode import RAGMode

from .schema import (
    CsvLoadResponse,
    DocumentUploadResponse,
    FileIngestResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter()


# ── Search ──


@router.post("/search")
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
        logging.exception(e)
        return SearchResponse(success=False, status=f"搜索失败: {e!s}", results=[])


# ── Document Ingestion ──


@router.post("/documents/upload")
async def api_upload_document(file: UploadFile) -> DocumentUploadResponse:
    try:
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
        logging.exception(e)
        return DocumentUploadResponse(success=False, status=f"文档上传失败: {e!s}", doc_ids=[])


@router.post("/documents/load-csv")
async def api_load_csv(
    file: UploadFile,
    adapter: Annotated[str, Body(embed=True)] = "philamuseum_raw",
) -> CsvLoadResponse:
    try:
        suffix = os.path.splitext(file.filename or "")[1]  # noqa: PTH122
        if suffix.lower() != ".csv":
            return CsvLoadResponse(success=False, status="仅支持 CSV 文件", artifact_count=0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        if adapter == "philamuseum":
            adp = PhilaMuseumAdapter()
        elif adapter == "philamuseum_raw":
            adp = PhilaMuseumRawAdapter()
        else:
            return CsvLoadResponse(success=False, status=f"未知适配器: {adapter}", artifact_count=0)

        rows = adp.load_csv(tmp_path)
        pathlib.Path(tmp_path).unlink()  # noqa: ASYNC240

        if not rows:
            return CsvLoadResponse(success=False, status="CSV 中没有有效数据行", artifact_count=0)

        artifact_store = ArtifactStore()
        ids = await artifact_store.ainsert_artifacts(rows)
        return CsvLoadResponse(
            success=True,
            status=f"已导入 {len(ids)} 条文物记录到 ArtifactStore",
            artifact_count=len(ids),
        )
    except Exception as e:
        logging.exception(e)
        return CsvLoadResponse(success=False, status=f"CSV 加载失败: {e!s}", artifact_count=0)


@router.post("/documents/ingest-artifacts")
async def api_ingest_artifacts(
    museum: str | None = None,
    limit: int | None = None,
    use_llm: bool = False,
) -> FileIngestResponse:
    try:
        doc_store = DocumentStore()
        file_ids = await doc_store.alingest_artifacts(museum=museum, limit=limit, use_llm=use_llm)
        return FileIngestResponse(
            success=True,
            status="文物数据提取成功",
            file_ids=[str(f) for f in file_ids],
        )
    except Exception as e:
        logging.exception(e)
        return FileIngestResponse(success=False, status=f"文物数据提取失败: {e!s}", file_ids=[])
