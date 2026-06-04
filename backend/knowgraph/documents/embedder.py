import logging
import os
from collections.abc import Sequence

import httpx

from .models import Document

MODEL_URL = "https://api.siliconflow.cn"
EMBEDDING_UID = "Qwen/Qwen3-VL-Embedding-8B"
RERANKER_UID = "Qwen/Qwen3-VL-Reranker-8B"
EMBEDDING_DIMS = 1024
API_KEY = os.environ.get("SILICONFLOW_API_KEY")

_MAX_RETRIES = 3


async def _retry_post(url: str, json: dict, headers: dict, time_out: float = 60.0) -> dict:
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=time_out) as client:
                response = await client.post(url, json=json, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            logging.warning("HTTP 请求失败 (第 %d/%d 次): %s，重试中", attempt, _MAX_RETRIES, exc)
    raise RuntimeError("unreachable")


def _build_embedding_input(
    documents: Sequence[Document | str],
    image_urls: Sequence[str | None] | None = None,
) -> list[str | dict | list[dict]]:
    items: list[str | dict | list[dict]] = []
    has_images = image_urls and any(image_urls)

    for i, d in enumerate(documents):
        text = d.content if isinstance(d, Document) else d
        img_url = image_urls[i] if image_urls and i < len(image_urls) else None

        if not img_url and isinstance(d, Document) and d.image_url:
            img_url = d.image_url

        if img_url and has_images:
            items.append([{"text": text}, {"image": img_url}])
        elif img_url:
            items.append([{"text": text}, {"image": img_url}])
        else:
            items.append(text)

    return items


async def aembed_documents(
    documents: Sequence[Document | str],
    image_urls: Sequence[str | None] | None = None,
) -> list[list[float]]:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "model": EMBEDDING_UID,
        "input": _build_embedding_input(documents, image_urls),
        "encoding_format": "float",
        "dimensions": EMBEDDING_DIMS,
    }

    results = await _retry_post(f"{MODEL_URL}/v1/embeddings", json=payload, headers=headers)
    return [obj["embedding"] for obj in results["data"]]


def _build_rerank_document(d: Document | str) -> str | dict:
    if isinstance(d, str):
        return d
    if d.image_url:
        return {"text": d.content, "image": d.image_url}
    return d.content


async def arerank_scores(
    query: str,
    documents: Sequence[Document | str],
) -> dict[int, float]:
    if not documents:
        return {}

    doc_inputs = [_build_rerank_document(d) for d in documents]

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "model": RERANKER_UID,
        "query": query,
        "documents": doc_inputs,
        "return_documents": False,
    }

    results = await _retry_post(f"{MODEL_URL}/v1/rerank", json=payload, headers=headers)
    return {item["index"]: item["relevance_score"] for item in results["results"]}


async def arerank_documents(
    query: str,
    documents: Sequence[Document | str],
    topn: int | None = None,
) -> list[Document]:
    if not documents:
        return []

    score_map = await arerank_scores(query, documents)

    reranked_docs: list[Document] = []
    for idx, src in enumerate(documents):
        score = score_map.get(idx)
        if score is None:
            continue
        if isinstance(src, Document):
            doc = src.model_copy()
            doc.query_score = score
        else:
            doc = Document(content=src, query_score=score)
        reranked_docs.append(doc)

    reranked_docs.sort(key=lambda d: d.query_score or 0, reverse=True)
    if topn is not None:
        reranked_docs = reranked_docs[:topn]
    return reranked_docs
