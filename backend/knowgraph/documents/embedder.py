import logging
import os
from collections.abc import Sequence
from copy import deepcopy
from typing import cast

import httpx

from .models import Document

MODEL_URL = "https://api.siliconflow.cn"
EMBEDDING_UID = "BAAI/bge-m3"
RERANKER_UID = "BAAI/bge-reranker-v2-m3"
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


async def aembed_documents(documents: Sequence[Document | str]) -> list[list[float]]:
    input_texts = [d.content if isinstance(d, Document) else d for d in documents]

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "model": EMBEDDING_UID,
        "input": input_texts,
        "encoding_format": "float",
    }

    results = await _retry_post(f"{MODEL_URL}/v1/embeddings", json=payload, headers=headers)
    return [obj["embedding"] for obj in results["data"]]


async def arerank_documents(
    query: str,
    documents: Sequence[Document | str],
    topn: int | None = None,
    skip_sorting: bool = False,
) -> list[Document]:
    if not documents:
        return []

    input_texts = [d.content if isinstance(d, Document) else d for d in documents]

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "model": RERANKER_UID,
        "query": query,
        "documents": input_texts,
        "return_documents": False,
    }

    results = await _retry_post(f"{MODEL_URL}/v1/rerank", json=payload, headers=headers)

    results_list = results["results"]
    if skip_sorting:
        reranked_docs = list(deepcopy(documents))
        for item in results_list:
            if isinstance(documents[item["index"]], Document):
                reranked_docs[item["index"]].query_score = item["relevance_score"]
            else:
                reranked_docs[item["index"]] = Document(
                    content=reranked_docs[item["index"]],
                    query_score=item["relevance_score"],
                )
        reranked_docs = cast("list[Document]", reranked_docs)
    else:
        reranked_docs = [documents[item["index"]] for item in results_list]
        scores = [item["relevance_score"] for item in results_list]
        for doc, score in zip(reranked_docs, scores, strict=False):
            doc.query_score = score
        if topn is not None:
            reranked_docs = reranked_docs[:topn]
    return reranked_docs
