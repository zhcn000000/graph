import logging
from collections.abc import AsyncIterator

import spacy
from asyncer import asyncify
from spacy.language import Language

from knowgraph.documents.models import Document

from .tokenizer import get_tokenizer

_nlp: Language | None = None


async def asplit_content(content: str, chunk_size: int = 512, chunk_overlap: int = 32) -> AsyncIterator[str]:
    global _nlp
    if _nlp is None:
        logging.info("Initializing spaCy pipeline...")
        _nlp = spacy.load("zh_core_web_trf")

    try:
        assert _nlp is not None
        doc = await asyncify(_nlp)(content)
    except Exception:
        yield content
        return

    sentences = [sent.text for sent in doc.sents]
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


async def asplit_document(
    document: Document,
    chunk_size: int = 512,
    chunk_overlap: int = 32,
) -> AsyncIterator[Document]:
    async for chunk in asplit_content(document.content, chunk_size, chunk_overlap):
        yield Document(
            content=chunk,
            name=document.name,
            link=document.link,
            metadata=document.metadata,
            entities=document.entities,
            triples=document.triples,
        )
