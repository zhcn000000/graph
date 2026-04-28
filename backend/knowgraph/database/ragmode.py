import operator
from collections import Counter
from typing import NamedTuple
from uuid import UUID

from knowgraph.documents.converter import aload_documents
from knowgraph.documents.models import Document
from knowgraph.documents.splitter import asplit_content, asplit_documents
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.embeddings.embedder import aembed_documents, arerank_documents
from knowgraph.utils.file import FileStream
from sqlalchemy import Float, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from .database import DatabaseManager
from .document import DocumentStore
from .rag import RAGConfig
from .source import SourceStore
from .tables import DocumentTable, RAGRelation, Source
from .types import BM25Vector


class QueryDocumentResult(NamedTuple):
    content: str
    source_name: str
    score: float


class RAGMode:
    def __init__(self, dbname: str = "data") -> None:
        self.__source = SourceStore(dbname)
        self.__db = DatabaseManager(dbname)

    async def aadd_rag_relation(self, rag_id: UUID, file_ids: UUID | list[UUID]) -> list[UUID]:
        if not file_ids:
            return []
        if isinstance(file_ids, UUID):
            file_ids = [file_ids]
        async with self.__db.asession() as session:
            stmt = (
                insert(RAGRelation)
                .values([{"rag_id": rag_id, "file_id": file_id} for file_id in file_ids])
                .on_conflict_do_nothing(index_elements=[col(RAGRelation.rag_id), col(RAGRelation.file_id)])
                .returning(col(RAGRelation.file_id))
            )
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall()]

    async def aremove_rag_relation(self, rag_id: UUID, file_ids: list[UUID] | UUID | None = None) -> list[UUID]:
        if isinstance(file_ids, UUID):
            file_ids = [file_ids]
        async with self.__db.asession() as session:
            stmt = delete(RAGRelation).where(col(RAGRelation.rag_id) == rag_id)
            if file_ids:
                stmt = stmt.where(col(RAGRelation.file_id).in_(file_ids))
            stmt = stmt.returning(col(RAGRelation.file_id))
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall()]

    async def aadd_documents(self, documents: list[Document]) -> list[UUID]:
        if not documents:
            return []

        async with self.__db.asession() as session:
            insert_values = []
            for doc in documents:
                docs = [doc]
                docs.extend([
                    Document(
                        content=chunk,
                        metadata=doc.metadata,
                        source_name=doc.source_name,
                        source_hash=doc.source_hash,
                    )
                    async for chunk in asplit_content(doc.content, chunk_size=512, chunk_overlap=64)
                ])
                filter_docs = []
                seen_contents = set()
                for doc in docs:
                    if doc.content not in seen_contents:
                        filter_docs.append(doc)
                        seen_contents.add(doc.content)
                docs = filter_docs
                vectors = await aembed_documents(docs)
                token_counts = await atokenize_content(doc.content)
                insert_values.append({
                    "file_id": select(col(Source.id)).where(col(Source.hash) == doc.source_hash).scalar_subquery(),
                    "content": doc.content,
                    "vector": vectors,
                    "bmvector": token_counts,
                })
            stmt = insert(DocumentTable).values(insert_values).returning(col(DocumentTable.id))
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall()]

    async def adelete_documents(self, ids: list[UUID] | None = None) -> bool | None:
        if not ids:
            return False
        uid_list = [UUID(id_) if isinstance(id_, str) else id_ for id_ in ids]
        async with self.__db.asession() as session:
            stmt = delete(DocumentTable).where(col(DocumentTable.id).in_(uid_list))
            result = await session.execute(stmt)
            await session.commit()
        return (result.rowcount or 0) > 0  # type: ignore

    @staticmethod
    async def _vector_search(
        queries: list[str],
        topn: int,
        session,
        rag_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
    ) -> list[UUID]:
        query_vector = await aembed_documents(queries)

        vector_stmt = select(col(DocumentTable.id))
        if rag_id or file_ids:
            vector_stmt = vector_stmt.join(Source, col(DocumentTable.file_id) == col(Source.id))
        if rag_id:
            vector_stmt = vector_stmt.join(RAGRelation, col(Source.id) == col(RAGRelation.file_id))
            vector_stmt = vector_stmt.where(col(RAGRelation.rag_id) == rag_id)
        if file_ids:
            vector_stmt = vector_stmt.where(col(Source.id).in_(file_ids))
        if regex:
            vector_stmt = vector_stmt.where(col(DocumentTable.content).op("~")(regex))

        vector_stmt = vector_stmt.order_by(col(DocumentTable.vector).op("@#", return_type=Float)(query_vector)).limit(
            topn,
        )

        vector_result = await session.execute(vector_stmt)
        return [row[0] for row in vector_result.fetchall()]

    @staticmethod
    async def _bm25_search(
        queries: list[str],
        topn: int,
        session,
        rag_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
    ) -> list[UUID]:
        query_count = Counter()
        for q in queries:
            query_count += await atokenize_content(q)

        bm25_stmt = select(col(DocumentTable.id))
        if rag_id or file_ids:
            bm25_stmt = bm25_stmt.join(Source, col(DocumentTable.file_id) == col(Source.id))
        if rag_id:
            bm25_stmt = bm25_stmt.join(RAGRelation, col(Source.id) == col(RAGRelation.file_id))
            bm25_stmt = bm25_stmt.where(col(RAGRelation.rag_id) == rag_id)
        if file_ids:
            bm25_stmt = bm25_stmt.where(col(Source.id).in_(file_ids))
        if regex:
            bm25_stmt = bm25_stmt.where(col(DocumentTable.content).op("~")(regex))

        bm25_stmt = bm25_stmt.order_by(
            col(DocumentTable.bmvector).neg_bm25_rank(  # type: ignore
                func.to_bm25query("idx_documents_bmvector", cast(query_count, BM25Vector)),
            ),
        ).limit(topn)

        bm25_result = await session.execute(bm25_stmt)
        return [row[0] for row in bm25_result.fetchall()]

    @staticmethod
    def _rrf_fusion(
        vector_results: list[UUID],
        bm25_results: list[UUID],
        topk: int,
        rrf_k: int = 60,
    ) -> list[UUID]:
        rrf_scores: dict[UUID, float] = {}

        for rank, doc_id in enumerate(vector_results, start=1):
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
            rrf_scores[doc_id] += 1.0 / (rrf_k + rank)

        for rank, doc_id in enumerate(bm25_results, start=1):
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
            rrf_scores[doc_id] += 1.0 / (rrf_k + rank)

        sorted_rrf_results = sorted(rrf_scores.items(), key=operator.itemgetter(1), reverse=True)[:topk]
        return [doc_id for doc_id, _ in sorted_rrf_results]

    async def ahyprid_search(
        self,
        queries: list[str],
        k: int = 4,
        rag_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
    ) -> list[Document]:
        topn = k * 5
        topk = k * 3
        rrf_k = 60

        async with self.__db.asession() as session:
            vector_results = await self._vector_search(
                queries=queries,
                topn=topn,
                session=session,
                rag_id=rag_id,
                file_ids=file_ids,
                regex=regex,
            )

            bm25_results = await self._bm25_search(
                queries=queries,
                topn=topn,
                session=session,
                rag_id=rag_id,
                file_ids=file_ids,
                regex=regex,
            )

            doc_ids = self._rrf_fusion(
                vector_results=vector_results,
                bm25_results=bm25_results,
                topk=topk,
                rrf_k=rrf_k,
            )

            if not doc_ids:
                return []

            doc_stmt = (
                select(
                    col(DocumentTable.id),
                    col(DocumentTable.content),
                    col(DocumentTable.meta),
                    col(Source.filename),
                    col(Source.hash),
                )
                .join(Source, col(Source.id) == col(DocumentTable.file_id))
                .where(col(DocumentTable.id).in_(doc_ids))
            )

            doc_result = await session.execute(doc_stmt)
            docs = {row[0]: row for row in doc_result.fetchall()}

            ordered_docs = [docs[doc_id] for doc_id in doc_ids if doc_id in docs]

            documents = [
                Document(
                    content=row[1],
                    metadata=row[2] or {},
                    source_name=row[3],
                    source_hash=row[4],
                )
                for row in ordered_docs
            ]

            documents = await arerank_documents("\n".join(queries), documents)
            return documents[:k]

    async def aget_by_ids(self, ids: list[str] | None = None) -> list[Document]:
        if not ids:
            return []
        uid_list = [UUID(id_) for id_ in ids]
        documents: list[Document] = []

        async with self.__db.asession() as session:
            stmt = select(DocumentTable).where(col(DocumentTable.id).in_(uid_list))
            result = await session.execute(stmt)
            for row in result.scalars().all():
                meta = dict(row.meta or {})
                documents.append(
                    Document(
                        content=row.content,
                        source_name=meta.get("file_name"),
                        source_hash=meta.get("source"),
                        metadata=meta,
                    ),
                )
            return documents

    async def aembed_documents(self, rag_id: UUID, files: list[FileStream]) -> None:
        conf = await RAGConfig().aget(rag_id=rag_id)
        assert conf is not None, "知识库不存在"

        documents = aload_documents(files)
        documents = asplit_documents(documents)
        documents = [doc async for doc in documents]
        await self.aadd_documents(documents)

    async def aquery_documents(
        self,
        rag_id: UUID,
        queries: list[str],
        regex: str | None = None,
        file_ids: list[UUID] | None = None,
    ) -> list[QueryDocumentResult]:
        conf = await RAGConfig().aget(rag_id)
        assert conf is not None, "知识库不存在"

        results = await self.ahyprid_search(queries, k=5, rag_id=rag_id, regex=regex, file_ids=file_ids)

        return [
            QueryDocumentResult(
                content=result.content,
                source_name=result.source_name or "untitled",
                score=result.query_score if result.query_score is not None else float("nan"),
            )
            for result in results
        ]

    async def aadd_embedding_documents(self, rag_id: UUID, files: list[FileStream]) -> list[UUID]:
        if isinstance(files, FileStream):
            files = [files]
        await self.__source.ainsert_files(files)
        file_ids = await self.__source.aget_id_by_hashs([file.file_hash for file in files])
        async with self.__db.asession() as session:
            stmt = select(col(DocumentTable.file_id)).where(
                col(DocumentTable.file_id).in_(file_ids),
            )
            existing = await session.execute(stmt)
            existing_file_ids = [row[0] for row in existing.fetchall()]
        existing_file_names = await self.__source.aget_name_by_ids(existing_file_ids)
        new_files = [file for file in files if file.name not in existing_file_names]
        if new_files:
            await self.aembed_documents(rag_id=rag_id, files=new_files)
        return await self.aadd_rag_relation(rag_id, file_ids)

    async def adelete_embedding_documents(self, rag_id: UUID, file_ids: list[UUID] | None = None) -> list[UUID]:
        removed = await self.aremove_rag_relation(rag_id, file_ids)
        if removed:
            await DocumentStore().adelete_orphan_by_file_ids(removed)
            await self.__source.adelete_orphan_files(removed)
        return removed

    async def acopy_embedding_documents(
        self,
        source_rag_id: UUID,
        target_rag_id: UUID,
        file_ids: list[UUID] | None = None,
    ) -> None:
        if file_ids is None:
            file_ids = await self.aget_embedding_documents(source_rag_id)
        async with self.__db.asession() as session:
            for file_id in file_ids:
                check_stmt = select(RAGRelation).where(
                    col(RAGRelation.rag_id) == target_rag_id,
                    col(RAGRelation.file_id) == file_id,
                )
                existing = await session.execute(check_stmt)
                if not existing.scalar_one_or_none():
                    stmt = insert(RAGRelation).values(rag_id=target_rag_id, file_id=file_id)
                    await session.execute(stmt)
            await session.commit()

    async def aget_embedding_documents(self, rag_id: UUID) -> list[UUID]:
        async with self.__db.asession() as session:
            stmt = select(col(RAGRelation.file_id)).where(col(RAGRelation.rag_id) == rag_id)
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]

    async def amove_embedding_documents(
        self,
        source_rag_id: UUID,
        target_rag_id: UUID,
        file_ids: list[UUID] | None = None,
    ) -> None:
        await self.acopy_embedding_documents(source_rag_id, target_rag_id, file_ids)
        await self.adelete_embedding_documents(source_rag_id, file_ids)

    async def areindex(self, reindex_vector: bool = True, reindex_bm25: bool = True) -> None:
        async with self.__db.acursor() as cur:
            if reindex_vector:
                await cur.execute("REINDEX INDEX CONCURRENTLY idx_documents_vector;")
            if reindex_bm25:
                await cur.execute("REINDEX INDEX CONCURRENTLY idx_documents_bmvector;")
