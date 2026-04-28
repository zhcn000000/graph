from collections.abc import AsyncIterator

from knowgraph.documents.models import Document
from knowgraph.utils.file import FileStream


async def aconvert_file(file_stream: FileStream) -> Document:
    return Document(
        content=file_stream.stream.getvalue().decode("utf-8", errors="ignore"),
        source_name=file_stream.name,
        source_hash=file_stream.file_hash,
    )


async def aload_documents(file_contents: list[FileStream]) -> AsyncIterator[Document]:
    for file_content in file_contents:
        raw_doc = await aconvert_file(file_content)

        source_name = file_content.name
        source_hash = file_content.file_hash
        meta = {"file_name": source_name, "file_hash": source_hash}
        yield Document(
            content=raw_doc.content,
            source_name=source_name,
            source_hash=source_hash,
            metadata=meta,
        )
