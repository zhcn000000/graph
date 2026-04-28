from collections.abc import Sequence

import httpx

from knowgraph.utils.environments import VLLM_HOST, VLLM_PORT, VLLM_PROTOCOL

from ..documents.models import Document

MODEL_URL = f"{VLLM_PROTOCOL}://{VLLM_HOST}:{VLLM_PORT}"
EMBEDDING_UID = "qwen3-embedding"
RERANKER_UID = "qwen3-reranker"
API_KEY = None


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

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{MODEL_URL}/v1/embeddings",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        results = response.json()

    return [obj["embedding"] for obj in results["data"]]


async def arerank_documents(query: str, documents: Sequence[Document | str], topn: int | None = None) -> list[Document]:
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

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{MODEL_URL}/v1/rerank",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        results = response.json()

    results = results["results"]
    reranked_docs = [documents[item["index"]] for item in results]
    scores = [item["relevance_score"] for item in results]
    for doc, score in zip(reranked_docs, scores, strict=False):
        doc.query_score = score
    if topn is not None:
        reranked_docs = reranked_docs[:topn]
    return reranked_docs
