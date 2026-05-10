from collections.abc import AsyncIterator
from typing import overload

from asyncer import asyncify

from knowgraph.documents.models import Document, get_nlp


@overload
async def asplit_content(content: str, chunk_size: int = 512, chunk_overlap: int = 32) -> AsyncIterator[str]: ...
@overload
async def asplit_content(
    content: Document, chunk_size: int = 512, chunk_overlap: int = 32
) -> AsyncIterator[Document]: ...
async def asplit_content(
    content: str | Document, chunk_size: int = 512, chunk_overlap: int = 32
) -> AsyncIterator[str] | AsyncIterator[Document]:
    if isinstance(content, str):
        nlp = get_nlp()
        doc = await asyncify(nlp)(content)
        sents = list(doc.sents)
        if not sents:
            return

        current_text = ""
        current_tokens = 0
        overlap_sentences: list[tuple[str, int]] = []

        for sent in sents:
            sent_text = sent.text
            sent_tokens = len(sent)
            if current_tokens + sent_tokens <= chunk_size:
                current_text += sent_text
                current_tokens += sent_tokens
                overlap_sentences.append((sent_text, sent_tokens))
            else:
                if current_text:
                    yield current_text
                overlap_text = ""
                overlap_token_count = 0
                overlap_sent_list: list[tuple[str, int]] = []
                for os_text, os_tokens in reversed(overlap_sentences):
                    if overlap_token_count + os_tokens <= chunk_overlap:
                        overlap_text = os_text + overlap_text
                        overlap_token_count += os_tokens
                        overlap_sent_list.insert(0, (os_text, os_tokens))
                    else:
                        break

                current_text = overlap_text + sent_text
                current_tokens = overlap_token_count + sent_tokens
                overlap_sentences = overlap_sent_list + [(sent_text, sent_tokens)]

        if current_text:
            yield current_text
    elif isinstance(content, Document):
        async for chunk in asplit_content(content.content, chunk_size, chunk_overlap):  # type: ignore
            yield Document(
                content=chunk,
                name=content.name,
                link=content.link,
                metadata=content.metadata,
                entities=content.entities,
                triples=content.triples,
            )
