import logging
import warnings
from pathlib import Path
from uuid import UUID

from asyncer import create_task_group
from networkx import DiGraph
from sqlalchemy import cast, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from knowgraph.documents.converter import aconvert_file
from knowgraph.documents.embedder import aembed_documents
from knowgraph.documents.models import Document
from knowgraph.documents.tokenizer import atokenize_document
from knowgraph.graph.schema import (
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipInfo,
    RelationshipType,
)
from knowgraph.graph.triples import LLMExtractor, classify_entity_types_batch, compute_triples_strength_batch

from .database import DatabaseManager
from .graph import AgeGraphManager
from .tables import ArtifactRawTable, DocumentTable
from .types import BM25Vector


def build_artifact_triples(artifact: dict) -> list[ExtractedTriple]:
    title = artifact.get("title", "")
    description = artifact.get("description")
    museum = artifact.get("museum", "")
    period = artifact.get("period")
    material = artifact.get("material")
    atype = artifact.get("type")
    location = artifact.get("location")

    triples: list[ExtractedTriple] = []

    if museum and title:
        triples.append(
            ExtractedTriple(
                subject=ExtractedEntity(name=title, entity_type=EntityType.ARTIFACT),
                predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
                object=ExtractedEntity(name=museum, entity_type=EntityType.MUSEUM),
                description=description or f"{title} 收藏于 {museum}",
            ),
        )

    if period:
        triples.append(
            ExtractedTriple(
                subject=ExtractedEntity(name=title, entity_type=EntityType.ARTIFACT),
                predicate=RelationshipInfo(predicate=RelationshipType.BELONGS_TO_DYNASTY),
                object=ExtractedEntity(name=period, entity_type=EntityType.DYNASTY),
                description=f"{title} 属于 {period}",
            ),
        )

    if material:
        triples.append(
            ExtractedTriple(
                subject=ExtractedEntity(name=title, entity_type=EntityType.ARTIFACT),
                predicate=RelationshipInfo(predicate=RelationshipType.MADE_OF_MATERIAL),
                object=ExtractedEntity(name=material, entity_type=EntityType.MATERIAL),
                description=f"{title} 材质为 {material}",
            ),
        )

    if atype:
        triples.append(
            ExtractedTriple(
                subject=ExtractedEntity(name=title, entity_type=EntityType.ARTIFACT),
                predicate=RelationshipInfo(predicate=RelationshipType.IS_TYPE_OF),
                object=ExtractedEntity(name=atype, entity_type=EntityType.ARTIFACT_TYPE),
                description=f"{title} 类型为 {atype}",
            ),
        )

    if location and museum:
        triples.append(
            ExtractedTriple(
                subject=ExtractedEntity(name=museum, entity_type=EntityType.MUSEUM),
                predicate=RelationshipInfo(predicate=RelationshipType.LOCATED_AT),
                object=ExtractedEntity(name=location, entity_type=EntityType.LOCATION),
                description=f"{museum} 位于 {location}",
            ),
        )

    return triples


def _build_doc_from_artifact(artifact: dict) -> Document:
    triples = build_artifact_triples(artifact)
    entity_uris = list({uri for t in triples for uri in (t.subject.uri, t.object.uri)})

    title = artifact.get("title", "")
    content_parts = [title]
    if artifact.get("museum"):
        content_parts.append(artifact["museum"])
    if artifact.get("period"):
        content_parts.append(artifact["period"])
    if artifact.get("type"):
        content_parts.append(artifact["type"])
    if artifact.get("material"):
        content_parts.append(artifact["material"])
    if artifact.get("description"):
        content_parts.append(artifact["description"])

    image_url = artifact.get("image_url") or None
    artifact_id_str = artifact.get("artifact_id")
    artifact_id = UUID(artifact_id_str) if artifact_id_str else None

    return Document(
        content="\n".join(content_parts),
        name=title or "Untitled",
        link=artifact.get("detail_url"),
        metadata={k: v for k, v in artifact.items() if k not in ("artifact_id", "image_data") and v is not None},
        entities=entity_uris,
        triples=triples,
        artifact_id=artifact_id,
        image_url=image_url,
    )


class DocumentStore:
    def __init__(self, dbname: str | None = None) -> None:
        self.__db = DatabaseManager(dbname)
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

    async def _check_duplicate(
        self,
        vector: list[float],
        bmvector: dict[int, int],
        threshold: float,
    ) -> bool:
        async with self.__db.asession() as session:
            stmt = (
                select(
                    col(DocumentTable.id),
                    col(DocumentTable.vector).l2_distance(vector).label("sim"),  # type: ignore
                    col(DocumentTable.bmvector)
                    .neg_bm25_rank(  # type: ignore
                        func.to_bm25query("idx_documents_bmvector", cast(bmvector, BM25Vector)),
                    )
                    .label("bm25_sim"),
                )
                .order_by(
                    col(DocumentTable.bmvector)
                    .neg_bm25_rank(  # type: ignore
                        func.to_bm25query("idx_documents_bmvector", cast(bmvector, BM25Vector)),
                    )
                    .label("bm25_sim")
                    .desc(),
                )
                .limit(5)
            )
            result = await session.execute(stmt)
            rows = result.fetchall()
            if rows:
                best_row = max(rows, key=lambda r: r[1] or 0)
                sim = best_row[1] or 0
                bm25_sim = best_row[2] or 0
                logging.info("与最近文档相似度: vector=%.4f, bm25=%.4f", sim, bm25_sim)
                return sim >= threshold
            return False

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
                        "name": t.subject.canonical_name,
                        "raw_name": t.subject.name,
                    },
                )
                graph.add_node(
                    t.object.uri,
                    label=t.object.entity_type.value.capitalize(),
                    properties={
                        "entity_type": t.object.entity_type.value,
                        "name": t.object.canonical_name,
                        "raw_name": t.object.name,
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
        use_llm: bool = False,
        dedup_threshold: float = 0.95,
    ) -> list[UUID]:
        if not documents:
            return []

        all_doc_ids: list[UUID] = []
        full_graph = DiGraph()
        insert_values: list[dict] = []
        start_idx = await self._next_document_index()
        skipped = 0
        async with self.__db.asession() as session:
            existing_artifact_ids: set[UUID] = set()
            cand_ids = [d.artifact_id for d in documents if d.artifact_id]
            if cand_ids:
                exist_stmt = (
                    select(col(DocumentTable.artifact_id))
                    .where(col(DocumentTable.artifact_id).in_(cand_ids))
                    .distinct()
                )
                exist_result = await session.execute(exist_stmt)
                existing_artifact_ids = {row[0] for row in exist_result.fetchall()}

            active_docs = [d for d in documents if not (d.artifact_id and d.artifact_id in existing_artifact_ids)]
            skipped += len(documents) - len(active_docs)

            if not active_docs:
                return []

            # Phase 1: parallel LLM extraction
            if use_llm:
                async with create_task_group() as tg:
                    llm_tasks = [tg.soonify(self._extract_llm_triples)(d) for d in active_docs]
                llm_results = [t.value for t in llm_tasks]
                for doc, result in zip(active_docs, llm_results, strict=True):
                    if isinstance(result, BaseException):
                        warnings.warn(
                            f"LLM extraction failed for {doc.name}: {result}",
                            UserWarning,
                            stacklevel=2,
                        )
                    elif result:
                        doc.triples = doc.triples + result

            # Phase 1.5: classify entity types via reranker (ArtifactType/Material/Dynasty)
            docs_with_triples = [d for d in active_docs if d.triples]
            if docs_with_triples:
                await classify_entity_types_batch([d.triples for d in docs_with_triples])

            # Phase 2: batch triple strength (mutates triples in-place)
            if docs_with_triples:
                await compute_triples_strength_batch([d.triples for d in docs_with_triples])

            for d in active_docs:
                entity_uris: set[str] = set()
                entity_uris |= self._triples_to_networkx(d.triples, full_graph)
                entity_uris |= set(d.entities)
                d.entities = list(entity_uris)

            # Phase 3: batch embed
            async def embed_single_document(d: Document) -> list[float]:
                try:
                    vec = await aembed_documents([d])
                    return vec[0]
                except Exception:
                    if d.image_url:
                        warnings.warn(
                            f"Embedding failed for document with image {d.image_url}, retrying without image.",
                            UserWarning,
                            stacklevel=2,
                        )
                        d.image_url = None
                        vec = await aembed_documents([d])
                        return vec[0]
                    raise

            async with create_task_group() as tg:
                embed_tasks = [tg.soonify(embed_single_document)(d) for d in active_docs]
            all_vectors = [t.value for t in embed_tasks]

            # Phase 4: parallel tokenize
            async with create_task_group() as tg:
                tokenize_tasks = [tg.soonify(atokenize_document)(d.content) for d in active_docs]
            all_bmvectors = [tokenize_tasks[i].value for i in range(len(active_docs))]
            # Phase 5: concurrent dedup check + collect inserts
            to_check = list(zip(active_docs, all_vectors, all_bmvectors, strict=True))
            if dedup_threshold > 0:
                async with create_task_group() as tg:
                    check_tasks = [
                        tg.soonify(self._check_duplicate)(vec, bmvec, dedup_threshold) for _, vec, bmvec in to_check
                    ]
                is_dups = [t.value for t in check_tasks]
            else:
                is_dups = [False] * len(to_check)

            for doc_idx, ((doc, vec, bmvec), is_dup) in enumerate(
                zip(to_check, is_dups, strict=True),
                start_idx,
            ):
                if is_dup:
                    skipped += 1
                    continue

                insert_values.append({
                    "artifact_id": doc.artifact_id,
                    "content": doc.content,
                    "vector": vec,
                    "bmvector": bmvec,
                    "entities": doc.entities,
                    "meta": doc.metadata,
                    "image_url": doc.image_url,
                    "document_index": doc_idx,
                })

            if skipped:
                logging.info("去重跳过 %d 个重复文档", skipped)

            if insert_values:
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
        use_llm: bool = False,
        dedup_threshold: float = 0.95,
    ) -> list[UUID]:
        if not documents:
            return []

        for doc in documents:
            if doc.name and doc.link:
                doc.metadata.setdefault("name", doc.name)
                doc.metadata.setdefault("link", doc.link)

        return await self.aadd_documents(documents, use_llm=use_llm, dedup_threshold=dedup_threshold)

    async def aload_from_document(self, file_path: str | Path) -> list[UUID]:
        file_path = Path(file_path)
        doc = await aconvert_file(file_path)
        doc.name = file_path.stem
        doc.link = f"file://{file_path.absolute()}"
        doc.metadata = {"file_name": file_path.name}

        return await self.ainsert_documents([doc], use_llm=True)

    async def alingest_artifacts(
        self,
        museum: str | None = None,
        limit: int | None = None,
        artifact_ids: list[UUID] | None = None,
        use_llm: bool = False,
        skip_ingested: bool = True,
        dedup_threshold: float = 0.95,
    ) -> list[UUID]:

        async with self.__db.asession() as session:
            stmt = select(ArtifactRawTable)
            if artifact_ids:
                stmt = stmt.where(col(ArtifactRawTable.id).in_(artifact_ids))
            elif museum:
                stmt = stmt.where(col(ArtifactRawTable.museum) == museum)
            if skip_ingested:
                stmt = stmt.where(
                    ~exists().where(
                        col(DocumentTable.artifact_id) == col(ArtifactRawTable.id),
                    ),
                )
            stmt = stmt.order_by(col(ArtifactRawTable.id))
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            artifact_rows = list(result.scalars().all())

            artifact_dicts: list[dict] = []
            for a in artifact_rows:
                artifact_dicts.append({
                    "object_id": a.object_id or "",
                    "title": a.title or "Untitled",
                    "period": a.period or "",
                    "type": a.type or "",
                    "material": a.material or "",
                    "description": a.description or "",
                    "dimensions": a.dimensions or "",
                    "museum": a.museum or "",
                    "location": a.location or "",
                    "detail_url": a.detail_url or "",
                    "image_url": a.image_url or "",
                    "credit_line": a.credit_line or "",
                    "accession_number": a.accession_number or "",
                    "artist": a.artist or "",
                    "crawl_date": str(a.crawl_date) if a.crawl_date else "",
                    "artifact_id": str(a.id),
                })

        if not artifact_dicts:
            return []

        documents: list[Document] = []

        for artifact_dict in artifact_dicts:
            doc = _build_doc_from_artifact(artifact_dict)
            doc.metadata["artifact_id"] = artifact_dict["artifact_id"]
            documents.append(doc)

        return await self.ainsert_documents(documents, use_llm=use_llm, dedup_threshold=dedup_threshold)

    async def aremove_documents(self, artifact_ids: list[UUID] | UUID | None = None) -> list[UUID]:
        if isinstance(artifact_ids, UUID):
            artifact_ids = [artifact_ids]
        if not artifact_ids:
            return []
        async with self.__db.asession() as session:
            stmt = (
                delete(DocumentTable)
                .where(col(DocumentTable.artifact_id).in_(artifact_ids))
                .returning(col(DocumentTable.artifact_id))
            )
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall() if row[0] is not None]

    async def areindex(self, reindex_vector: bool = True, reindex_bm25: bool = True) -> None:
        async with self.__db.acursor() as cur:
            if reindex_vector:
                await cur.execute("REINDEX INDEX CONCURRENTLY idx_documents_vector;")
            if reindex_bm25:
                await cur.execute("REINDEX INDEX CONCURRENTLY idx_documents_bmvector;")
