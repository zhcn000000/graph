import warnings
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pandas as pd
from networkx import DiGraph
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from knowgraph.documents.converter import aconvert_file
from knowgraph.documents.embedder import aembed_documents
from knowgraph.documents.models import Document
from knowgraph.documents.splitter import asplit_document
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.graph.schema import ExtractedTriple
from knowgraph.graph.triples import CSVRowInput, LLMExtractor

from .database import DatabaseManager
from .graph import AgeGraphManager
from .source import SourceStore
from .tables import ArtifactRawTable, DocumentTable


class DocumentStore:
    def __init__(self, dbname: str | None = None) -> None:
        self.__db = DatabaseManager(dbname)
        self.__source = SourceStore(dbname)
        self._graph_manager: AgeGraphManager | None = None
        self._extractor: LLMExtractor | None = None

    @property
    def graph_manager(self) -> AgeGraphManager:
        if self._graph_manager is None:
            self._graph_manager = AgeGraphManager(dbname=self.__db.dbname)
        return self._graph_manager

    @property
    def extractor(self) -> LLMExtractor:
        if self._extractor is None:
            self._extractor = LLMExtractor()
        return self._extractor

    async def _extract_llm_triples(self, doc: Document) -> list[ExtractedTriple]:
        try:
            return await self.extractor.aextract_from_document(doc)
        except Exception:
            warnings.warn(
                "LLM extraction call failed, continuing without extracted entities.",
                UserWarning,
                stacklevel=2,
            )
            return []

    @staticmethod
    def _triples_to_networkx(
        triples: list[ExtractedTriple],
        graph: DiGraph,
    ) -> set[str]:
        entity_uris: set[str] = set()
        for t in triples:
            try:
                graph.add_node(
                    t.subject.uri,
                    label=t.subject.entity_type.value.capitalize(),
                    properties={
                        "entity_type": t.subject.entity_type.value,
                        "name": t.subject.name,
                    },
                )
                graph.add_node(
                    t.object.uri,
                    label=t.object.entity_type.value.capitalize(),
                    properties={
                        "entity_type": t.object.entity_type.value,
                        "name": t.object.name,
                    },
                )
                graph.add_edge(
                    t.subject.uri,
                    t.object.uri,
                    label=t.predicate.predicate,
                    properties={
                        "relationship_type": t.predicate.predicate,
                        "description": t.description,
                        "connection_strength": t.predicate.strength,
                    },
                )
                entity_uris.add(t.subject.uri)
                entity_uris.add(t.object.uri)
            except ValueError as e:
                warnings.warn(
                    f"Skipping triple due to invalid entity URI: {e}",
                    UserWarning,
                    stacklevel=2,
                )
        return entity_uris

    async def _next_document_index(self) -> int:
        async with self.__db.asession() as session:
            stmt = select(func.coalesce(func.max(col(DocumentTable.document_index)), 0))
            result = await session.execute(stmt)
            return (result.scalar() or 0) + 1

    async def aadd_documents(
        self,
        documents: list[Document],
    ) -> list[UUID]:
        if not documents:
            return []

        all_doc_ids: list[UUID] = []
        full_graph = DiGraph()
        insert_values: list[dict] = []
        start_idx = await self._next_document_index()
        for doc_idx, doc in enumerate(documents, start_idx):
            file_id = doc.file_id
            if file_id is None and doc.name:
                warnings.warn(
                    f"Source not found for name '{doc.name}', skipping document.",
                    UserWarning,
                    stacklevel=2,
                )

            entity_uris: set[str] = set()
            doc_llm_triples = await self._extract_llm_triples(doc)
            doc.triples = doc.triples + doc_llm_triples
            entity_uris |= self._triples_to_networkx(doc.triples, full_graph)
            entity_uris |= set(doc.entities)

            chunk_idx = 0
            async for chunk in asplit_document(doc, chunk_size=4096, chunk_overlap=128):
                chunk_idx += 1
                sub_chunks = []
                async for sub_doc in asplit_document(chunk, chunk_size=512, chunk_overlap=32):
                    sub_chunks.append(sub_doc)
                vectors = await aembed_documents(sub_chunks)
                bmvector = await atokenize_content(chunk)

                insert_values.append({
                    "file_id": file_id,
                    "content": chunk.content,
                    "vector": vectors,
                    "bmvector": bmvector,
                    "entities": list(entity_uris),
                    "meta": doc.metadata,
                    "document_index": doc_idx,
                    "chunk_index": chunk_idx,
                })

        if insert_values:
            async with self.__db.asession() as session:
                stmt = insert(DocumentTable).values(insert_values).returning(col(DocumentTable.id))
                result = await session.execute(stmt)
                await session.commit()
                all_doc_ids = [row[0] for row in result.fetchall()]
        elif documents:
            warnings.warn(
                f"No documents were inserted out of {len(documents)} provided.",
                UserWarning,
                stacklevel=2,
            )

        if full_graph.number_of_nodes() > 0:
            await self.graph_manager.afrom_networkx(full_graph)

        return all_doc_ids

    async def adelete_by_file_ids(self, file_ids: Sequence[UUID]) -> int:
        file_ids = list(file_ids)
        if not file_ids:
            return 0
        async with self.__db.asession() as session:
            stmt = delete(DocumentTable).where(col(DocumentTable.file_id).in_(file_ids))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0  # type: ignore

    async def adelete_orphan_by_file_ids(self, file_ids: Sequence[UUID]) -> int:
        file_ids = list(file_ids)
        if not file_ids:
            return 0
        async with self.__db.asession() as session:
            stmt = delete(DocumentTable).where(col(DocumentTable.file_id).in_(file_ids))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0  # type: ignore

    async def adelete_documents(self, ids: list[UUID] | None = None) -> bool | None:
        if not ids:
            return False
        uid_list = [UUID(id_) if isinstance(id_, str) else id_ for id_ in ids]
        async with self.__db.asession() as session:
            stmt = delete(DocumentTable).where(col(DocumentTable.id).in_(uid_list))
            result = await session.execute(stmt)
            await session.commit()
        return (result.rowcount or 0) > 0  # type: ignore

    async def ainsert_documents(
        self,
        documents: list[Document],
    ) -> list[UUID]:
        if not documents:
            return []

        for doc in documents:
            if not doc.name:
                continue
            artifact_id_str = doc.metadata.get("artifact_id")
            artifact_id = UUID(artifact_id_str) if artifact_id_str else None
            doc.file_id = await self.__source.ainsert_source(name=doc.name, link=doc.link, artifact_id=artifact_id)
            if doc.file_id is None:
                doc.file_id = (await self.__source.aget_id_by_names([doc.name]))[0]

        await self.aadd_documents(documents)

        source_names = list({d.name for d in documents if d.name})
        if not source_names:
            return []
        return await self.__source.aget_id_by_names(source_names)

    @staticmethod
    def _build_doc_from_row_input(
        row_input: CSVRowInput,
    ) -> Document:
        triples = row_input.to_artifact_triples()

        structured_entities: list[str] = list({uri for t in triples for uri in (t.subject.uri, t.object.uri)})

        content_parts = [row_input.title]
        if row_input.museum:
            content_parts.append(row_input.museum)
        if row_input.period:
            content_parts.append(row_input.period)
        if row_input.type:
            content_parts.append(row_input.type)
        if row_input.material:
            content_parts.append(row_input.material)
        if row_input.description:
            content_parts.append(row_input.description)
        content_str = "\n".join(content_parts)

        return Document(
            content=content_str,
            name=row_input.title,
            link=row_input.detail_url,
            metadata=row_input.model_dump(),
            entities=structured_entities,
            triples=triples,
        )

    async def aload_from_document(self, file_path: str | Path) -> list[UUID]:
        file_path = Path(file_path)
        doc = await aconvert_file(file_path)
        doc.name = file_path.stem
        doc.link = f"file://{file_path.absolute()}"
        doc.metadata = {"file_name": file_path.name}

        return await self.ainsert_documents([doc])

    async def aload_from_csv(self, csv_path: str) -> list[UUID]:
        documents: list[Document] = []

        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                row_input = CSVRowInput(**{str(k): v for k, v in row_dict.items() if pd.notna(v)})
            except Exception as e:
                warnings.warn(f"Skipping invalid CSV row: {e}", UserWarning, stacklevel=2)
                continue

            doc = self._build_doc_from_row_input(row_input)
            documents.append(doc)

        return await self.ainsert_documents(documents)

    async def alingest_artifacts(
        self,
        museum: str | None = None,
        limit: int | None = None,
    ) -> list[UUID]:

        async with self.__db.asession() as session:
            stmt = select(ArtifactRawTable)
            if museum:
                stmt = stmt.where(col(ArtifactRawTable.museum) == museum)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            artifacts = list(result.scalars().all())

        if not artifacts:
            return []

        documents: list[Document] = []

        for artifact in artifacts:
            row_dict = {
                "object_id": artifact.object_id or "",
                "title": artifact.title or "Untitled",
                "period": artifact.period or None,
                "type": artifact.type or None,
                "material": artifact.material or None,
                "description": artifact.description or None,
                "dimensions": artifact.dimensions or None,
                "museum": artifact.museum,
                "location": artifact.location or None,
                "detail_url": artifact.detail_url or None,
                "image_url": artifact.image_url or None,
                "credit_line": artifact.credit_line or None,
                "accession_number": artifact.accession_number or None,
                "crawl_date": str(artifact.crawl_date) if artifact.crawl_date else None,
            }
            cleaned = {k: v for k, v in row_dict.items() if v is not None}

            try:
                row_input = CSVRowInput(**cleaned)
            except Exception as e:
                warnings.warn(f"Skipping artifact {artifact.id}: {e}", UserWarning, stacklevel=2)
                continue

            doc = self._build_doc_from_row_input(row_input)
            doc.metadata["artifact_id"] = str(artifact.id)
            documents.append(doc)

        return await self.ainsert_documents(documents)

    async def aremove_documents(self, file_ids: list[UUID] | UUID | None = None) -> list[UUID]:
        if isinstance(file_ids, UUID):
            file_ids = [file_ids]
        if not file_ids:
            return []
        async with self.__db.asession() as session:
            stmt = (
                delete(DocumentTable)
                .where(col(DocumentTable.file_id).in_(file_ids))
                .returning(col(DocumentTable.file_id))
            )
            result = await session.execute(stmt)
            await session.commit()
            removed = [row[0] for row in result.fetchall()]
        if removed:
            await self.__source.adelete_orphan_files(removed)
        return removed

    async def areindex(self, reindex_vector: bool = True, reindex_bm25: bool = True) -> None:
        async with self.__db.acursor() as cur:
            if reindex_vector:
                await cur.execute("REINDEX INDEX CONCURRENTLY idx_documents_vector;")
            if reindex_bm25:
                await cur.execute("REINDEX INDEX CONCURRENTLY idx_documents_bmvector;")
