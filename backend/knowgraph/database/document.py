import warnings
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pandas as pd
from networkx import DiGraph
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from knowgraph.documents.embedder import aembed_documents
from knowgraph.documents.models import Document
from knowgraph.documents.splitter import asplit_content
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.graph.triples import CSVRowInput, LLMExtractor

from .database import DatabaseManager
from .graph import AgeGraphManager
from .source import SourceStore
from .tables import ArtifactRawTable, DocumentTable, Source


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

    async def _extract_and_update_graph(self, content: str, full_graph: DiGraph) -> set[str]:
        try:
            triples = await self.extractor.aextract_from_document(Document(content=content))
        except Exception:
            warnings.warn(
                "LLM extraction call failed, continuing without extracted entities.",
                UserWarning,
                stacklevel=2,
            )
            return set()

        entity_uris: set[str] = set()
        for triple in triples:
            try:
                subject_label = triple.subject.entity_type.value.capitalize()
                object_label = triple.object.entity_type.value.capitalize()
                full_graph.add_node(
                    triple.subject.uri,
                    label=subject_label,
                    name=triple.subject.name,
                    entity_type=triple.subject.entity_type.value,
                )
                full_graph.add_node(
                    triple.object.uri,
                    label=object_label,
                    name=triple.object.name,
                    entity_type=triple.object.entity_type.value,
                )
                full_graph.add_edge(
                    triple.subject.uri,
                    triple.object.uri,
                    label=triple.predicate.value,
                    uri=f"cidoc:relationship/{triple.predicate.value}",
                    description=triple.description,
                )
                entity_uris.add(triple.subject.uri)
                entity_uris.add(triple.object.uri)
            except ValueError as e:
                warnings.warn(
                    f"Skipping triple due to invalid entity URI: {e}",
                    UserWarning,
                    stacklevel=2,
                )
        return entity_uris

    async def _next_document_index(self, session) -> int:
        stmt = select(func.coalesce(func.max(col(DocumentTable.document_index)), 0))
        result = await session.execute(stmt)
        return (result.scalar() or 0) + 1

    async def aadd_documents(
        self,
        documents: list[Document],
        extraction_contents: list[str | None] | None = None,
    ) -> list[UUID]:
        if not documents:
            return []

        all_doc_ids: list[UUID] = []
        full_graph = DiGraph()

        source_names = {doc.name for doc in documents if doc.name}
        file_id_map: dict[str, UUID] = {}
        if source_names:
            async with self.__db.asession() as pre_session:
                stmt = select(col(Source.id), col(Source.name)).where(
                    col(Source.name).in_(list(source_names)),
                )
                result = await pre_session.execute(stmt)
                file_id_map = {row[1]: row[0] for row in result.fetchall()}

        insert_values: list[dict] = []
        async with self.__db.asession() as session:
            next_doc_id = await self._next_document_index(session)

        for i, doc in enumerate(documents):
            file_id = file_id_map.get(doc.name or "")
            if file_id is None:
                warnings.warn(
                    f"Source not found for name '{doc.name}', skipping document.",
                    UserWarning,
                    stacklevel=2,
                )
                continue

            sub_chunks: list[str] = []
            async for chunk in asplit_content(doc.content, chunk_size=512, chunk_overlap=64):
                sub_chunks.append(chunk)
            if not sub_chunks:
                sub_chunks = [doc.content]

            seen: set[str] = set()
            sub_chunks = [c for c in sub_chunks if c not in seen and not seen.add(c)]

            sub_docs = [Document(content=c) for c in sub_chunks]
            vectors = await aembed_documents(sub_docs)

            bmvector = await atokenize_content(doc.content)

            entity_uris: set[str] = set()
            if extraction_contents is not None:
                extraction_content = extraction_contents[i] if i < len(extraction_contents) else None
                if extraction_content is not None:
                    entity_uris |= await self._extract_and_update_graph(extraction_content, full_graph)
            else:
                entity_uris |= await self._extract_and_update_graph(doc.content, full_graph)

            entity_uris |= set(doc.entities)

            for chunk_idx, chunk_content in enumerate(sub_chunks):
                insert_values.append({
                    "file_id": file_id,
                    "content": chunk_content,
                    "vector": vectors,
                    "bmvector": bmvector,
                    "entities": list(entity_uris),
                    "meta": doc.metadata,
                    "document_index": next_doc_id,
                    "chunk_index": chunk_idx,
                })

            next_doc_id += 1

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

    async def ainsert_document(
        self,
        name: str,
        content: str,
        link: str | None = None,
    ) -> UUID | None:
        source_id = await self.__source.ainsert_source(name=name, link=link)
        if source_id is None:
            existing_ids = await self.__source.aget_id_by_names([name])
            if existing_ids:
                source_id = existing_ids[0]
            else:
                return None

        doc = Document(
            content=content,
            name=name,
            link=link,
            metadata={"name": name, "link": link or ""},
        )

        await self.aadd_documents([doc])
        return source_id

    async def aload_from_document(self, file_path: str | Path) -> list[UUID]:
        from knowgraph.documents.converter import aconvert_file

        file_path = Path(file_path)
        doc = await aconvert_file(file_path)
        doc.name = file_path.stem
        doc.link = f"file://{file_path.absolute()}"
        doc.metadata = {"file_name": file_path.name}

        source_id = await self.__source.ainsert_source(name=doc.name, link=doc.link)
        if source_id is None:
            existing_ids = await self.__source.aget_id_by_names([doc.name])
            if existing_ids:
                source_id = existing_ids[0]
            else:
                return []

        doc_ids = await self.aadd_documents([doc])

        return doc_ids

    @staticmethod
    def _build_doc_and_source_from_row_input(
        row_input: CSVRowInput,
        structured_graph: DiGraph,
    ) -> tuple[Document, str | None, dict]:
        triples = row_input.to_artifact_triples()
        for triple in triples:
            structured_graph.add_node(
                triple.subject_uri,
                label=triple.subject_type.value.capitalize(),
                name=triple.subject_name,
                entity_type=triple.subject_type.value,
            )
            structured_graph.add_node(
                triple.object_uri,
                label=triple.object_type.value.capitalize(),
                name=triple.object_name,
                entity_type=triple.object_type.value,
            )
            rel_type = triple.predicate_uri.rsplit("/", 1)[-1]
            structured_graph.add_edge(triple.subject_uri, triple.object_uri, label=rel_type)

        structured_entities: list[str] = list({
            uri for triple in triples for uri in (triple.subject_uri, triple.object_uri)
        })

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

        doc = Document(
            content=content_str,
            name=row_input.title,
            link=row_input.detail_url,
            metadata=row_input.model_dump(),
            entities=structured_entities,
        )
        extraction_content = row_input.description or None
        source_info = {
            "name": row_input.title,
            "link": row_input.detail_url,
        }

        return doc, extraction_content, source_info

    async def _insert_artifact_batch(
        self,
        documents: list[Document],
        extraction_contents: list[str | None],
        source_infos: list[dict],
        structured_graph: DiGraph,
    ) -> list[UUID]:
        if not documents:
            return []

        if structured_graph.number_of_nodes() > 0:
            await self.graph_manager.afrom_networkx(structured_graph)

        async with self.__db.asession() as session:
            for info in source_infos:
                stmt = insert(Source).values(**info).on_conflict_do_nothing(index_elements=[col(Source.name)])
                await session.execute(stmt)
            await session.commit()

        await self.aadd_documents(documents, extraction_contents=extraction_contents)

        source_names = list({d.name for d in documents if d.name})
        file_ids: list[UUID] = []
        if source_names:
            file_ids = await self.__source.aget_id_by_names(source_names)

        return file_ids

    async def aload_from_csv(self, csv_path: str) -> list[UUID]:
        structured_graph = DiGraph()
        documents: list[Document] = []
        source_infos: list[dict] = []
        extraction_contents: list[str | None] = []

        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                row_input = CSVRowInput(**{str(k): v for k, v in row_dict.items() if pd.notna(v)})
            except Exception as e:
                warnings.warn(f"Skipping invalid CSV row: {e}", UserWarning, stacklevel=2)
                continue

            doc, extraction_content, source_info = self._build_doc_and_source_from_row_input(
                row_input, structured_graph
            )
            documents.append(doc)
            extraction_contents.append(extraction_content)
            source_infos.append(source_info)

        return await self._insert_artifact_batch(documents, extraction_contents, source_infos, structured_graph)

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

        structured_graph = DiGraph()
        documents: list[Document] = []
        source_infos: list[dict] = []
        extraction_contents: list[str | None] = []

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

            doc, extraction_content, source_info = self._build_doc_and_source_from_row_input(
                row_input, structured_graph
            )
            source_info["artifact_id"] = artifact.id
            documents.append(doc)
            extraction_contents.append(extraction_content)
            source_infos.append(source_info)

        return await self._insert_artifact_batch(documents, extraction_contents, source_infos, structured_graph)

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
