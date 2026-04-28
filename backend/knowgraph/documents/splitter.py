import os
from collections.abc import AsyncIterator

import httpx
import orjson
from asyncer import asyncify
from simplerag.documents.models import Document
from simplerag.utils.environments import DATA_ROOT, find_project_directory
from stanza import Document as StanzaDocument
from stanza import Pipeline

from .tokenizer import get_tokenizer

GH_PROXY = "https://gh-proxy.org/"
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT
os.environ["HUGGINGFACE_HUB_CACHE"] = str(DATA_ROOT / "huggingface")

_nlp: Pipeline | None = None


async def download_stanza_resource() -> None:
    async with httpx.AsyncClient() as client:
        resource_url = (
            GH_PROXY
            + "https://raw.githubusercontent.com/stanfordnlp/stanza-resources/refs/heads/main/resources_1.11.0.json"
        )
        response = await client.get(resource_url)
        content = response.json()
        content["url"] = (
            "https://hf-mirror.com/stanfordnlp/stanza-{lang}/resolve/v{resources_version}/models/{filename}"
        )
        model_dir = DATA_ROOT / "stanza"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "resources.json").write_bytes(orjson.dumps(content))


async def asplit_content(content: str, chunk_size: int = 512, chunk_overlap: int = 32) -> AsyncIterator[str]:
    global _nlp
    if _nlp is None:
        model_dir = DATA_ROOT / "stanza"
        project_root = find_project_directory()
        resource_json = project_root / "resources.json"
        if not model_dir.exists() or not resource_json.exists():
            await download_stanza_resource()

        _nlp = Pipeline(
            lang="zh-hans",
            processors="tokenize",
            tokenize_no_ssplit=False,
            dir=str(model_dir),
            download_method=2,
        )

    try:
        assert _nlp is not None
        doc: StanzaDocument = await asyncify(_nlp)(content)
    except Exception:
        yield content
        return

    sentences = [sent.text for sent in doc.sentences]
    if not sentences:
        return

    current_text = ""
    current_tokens = 0
    overlap_sentences = []

    for sent_text in sentences:
        sent_tokens = len(get_tokenizer().tokenize(sent_text))

        if current_tokens + sent_tokens <= chunk_size:
            current_text += sent_text
            current_tokens += sent_tokens
            overlap_sentences.append((sent_text, sent_tokens))
        else:
            if current_text:
                yield current_text

            overlap_text = ""
            overlap_token_count = 0
            for overlap_sent, overlap_sent_tokens in reversed(overlap_sentences):
                if overlap_token_count + overlap_sent_tokens <= chunk_overlap:
                    overlap_text = overlap_sent + overlap_text
                    overlap_token_count += overlap_sent_tokens
                else:
                    break

            current_text = overlap_text + sent_text
            current_tokens = overlap_token_count + sent_tokens
            overlap_sentences = (
                [(overlap_text + sent_text, overlap_token_count + sent_tokens)]
                if overlap_text
                else [(sent_text, sent_tokens)]
            )

    if current_text:
        yield current_text


async def asplit_documents(
    documents: AsyncIterator[Document],
    chunk_size: int = 2048,
    chunk_overlap: int = 128,
) -> AsyncIterator[Document]:
    async for chunk in documents:
        async for split_content in asplit_content(chunk.content, chunk_size, chunk_overlap):
            yield Document(
                content=split_content,
                source_name=chunk.source_name,
                source_hash=chunk.source_hash,
                metadata=chunk.metadata,
            )
