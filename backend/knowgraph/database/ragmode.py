import operator
from collections import Counter
from typing import NamedTuple
from uuid import UUID

from networkx import DiGraph, pagerank
from sqlalchemy import Float, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from knowgraph.documents.converter import aload_documents
from knowgraph.documents.embedder import aembed_documents, arerank_documents
from knowgraph.documents.models import Document
from knowgraph.documents.splitter import asplit_content, asplit_documents
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.graph.edge_strength import EdgeConnectionInfo, EdgeStrengthCalculator, TripleBasedEdgeQuerier
from knowgraph.graph.triples import LLMExtractor
from knowgraph.utils.file import FileStream

from .database import DatabaseManager
from .document import DocumentStore
from .graph import AgeGraphManager
from .rag import RAGConfig
from .source import SourceStore
from .tables import DocumentTable, RAGRelation, Source
from .types import BM25Vector


class QueryDocumentResult(NamedTuple):
    content: str
    source_name: str
    score: float


class GraphSearchResult(NamedTuple):
    entity_uri: str
    entity_name: str
    entity_type: str
    score: float
    path: DiGraph | None = None


class RAGMode:  # noqa: PLR0904
    def __init__(self, dbname: str = "data") -> None:
        self.__source = SourceStore(dbname)
        self.__db = DatabaseManager(dbname)
        self._graph_manager: AgeGraphManager | None = None
        self._edge_querier: TripleBasedEdgeQuerier | None = None
        self._edge_calculator: EdgeStrengthCalculator | None = None

    @property
    def graph_manager(self) -> AgeGraphManager:
        if self._graph_manager is None:
            self._graph_manager = AgeGraphManager(dbname=self.__db.dbname)
        return self._graph_manager

    @property
    def edge_querier(self) -> TripleBasedEdgeQuerier:
        if self._edge_querier is None:
            self._edge_querier = TripleBasedEdgeQuerier(graph_manager=self.graph_manager)
        return self._edge_querier

    @property
    def edge_calculator(self) -> EdgeStrengthCalculator:
        if self._edge_calculator is None:
            self._edge_calculator = EdgeStrengthCalculator(graph_manager=self.graph_manager)
        return self._edge_calculator

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

        extractor = LLMExtractor()
        all_doc_ids: list[UUID] = []
        full_graph = DiGraph()

        async with self.__db.asession() as session:
            for doc in documents:
                chunks = [doc]
                chunks.extend([
                    Document(
                        content=chunk,
                        metadata=doc.metadata,
                        source_name=doc.source_name,
                        source_hash=doc.source_hash,
                    )
                    async for chunk in asplit_content(doc.content, chunk_size=512, chunk_overlap=64)
                ])
                seen_contents = set()
                unique_chunks = [
                    c for c in chunks if c.content not in seen_contents and not seen_contents.add(c.content)
                ]

                vectors = await aembed_documents(unique_chunks)
                token_counts = await atokenize_content(doc.content)

                triples = await extractor.aextract_from_document(doc)
                entity_uris: set[str] = set()
                for triple in triples:
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
                    )
                    entity_uris.add(triple.subject.uri)
                    entity_uris.add(triple.object.uri)

                insert_values = []
                for chunk, vector in zip(unique_chunks, vectors, strict=False):
                    chunk.entities = list(entity_uris)
                    insert_values.append({
                        "file_id": select(col(Source.id)).where(col(Source.hash) == doc.source_hash).scalar_subquery(),
                        "content": chunk.content,
                        "vector": vector,
                        "bmvector": token_counts,
                        "entities": chunk.entities,
                    })

                stmt = insert(DocumentTable).values(insert_values).returning(col(DocumentTable.id))
                result = await session.execute(stmt)
                all_doc_ids.extend([row[0] for row in result.fetchall()])

            await session.commit()

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

    async def _collect_entity_uris(
        self,
        doc_ids: list[UUID],
        session,
    ) -> list[tuple[str, float]]:
        if not doc_ids:
            return []
        stmt = select(col(DocumentTable.entities)).where(col(DocumentTable.id).in_(doc_ids))
        result = await session.execute(stmt)
        counter: dict[str, int] = {}
        for row in result.fetchall():
            entities = row[0] or []
            for uri in entities:
                counter[uri] = counter.get(uri, 0) + 1

        total = sum(counter.values()) or 1
        ranked = sorted(counter.items(), key=operator.itemgetter(1), reverse=True)
        return [(uri, count / total) for uri, count in ranked]

    async def _graph_search(
        self,
        queries: list[str],
        topn: int,
        entity_uris_with_scores: list[tuple[str, float]],
        max_hops: int = 2,
        session=None,
    ) -> list[GraphSearchResult]:
        if not entity_uris_with_scores:
            return []

        entity_score_map: dict[str, float] = dict(entity_uris_with_scores)

        # Step 1: Batch lookup all vertices at once
        scan_uris = [uri for uri, _ in entity_uris_with_scores[: max(topn * 3, 30)]]
        vertex_cypher = """
        UNWIND $uris as uri
        MATCH (v {uri: uri})
        RETURN v.uri as uri, id(v) as id, v.name as name, v.entity_type as entity_type
        """
        vertex_rows = await self.graph_manager.aexecute_cypher(vertex_cypher, {"uris": scan_uris})
        vertex_map: dict[str, dict[str, object]] = {r["uri"]: r for r in vertex_rows}

        # Step 2: Traverse from each found vertex, build unified graph for PageRank
        unified_graph = DiGraph()
        for entity_uri, _ in entity_uris_with_scores[: max(topn * 2, 20)]:
            if entity_uri not in vertex_map:
                continue
            try:
                sub = await self.graph_manager.atraverse(entity_uri, max_hops=max_hops)
                unified_graph.add_nodes_from(sub.nodes(data=True))
                unified_graph.add_edges_from(sub.edges(data=True))
            except Exception:
                pass

        if unified_graph.number_of_nodes() == 0:
            return []

        # Step 3: PageRank with personalization from entity scores
        personalization: dict[str, float] = {}
        for node in unified_graph.nodes():
            personalization[node] = entity_score_map.get(node, 0.0)

        total_pers = sum(personalization.values())
        if total_pers > 0:
            pr_scores = pagerank(unified_graph, personalization=personalization)
        else:
            pr_scores = pagerank(unified_graph)

        # Step 4: Query edges by entity names via edge_querier
        names: list[str] = [
            str(vertex_map[uri]["name"])
            for uri in entity_score_map
            if uri in vertex_map and vertex_map[uri].get("name")
        ][:30]

        edges_by_name = await self.edge_querier.query_edges_by_entity_names(names)

        # Step 5: Re-rank edges against current query
        combined_query = " ".join(queries)
        all_edges: list[EdgeConnectionInfo] = []
        for edges in edges_by_name.values():
            all_edges.extend(edges)
        if all_edges:
            await self.edge_calculator.compute_strength_for_edges(combined_query, all_edges)

        # Step 6: Combine PageRank scores with edge strength
        graph_results: list[GraphSearchResult] = []
        seen_uris: set[str] = set()

        sorted_by_pr = sorted(pr_scores.items(), key=operator.itemgetter(1), reverse=True)

        for entity_uri, pr_score in sorted_by_pr:
            if entity_uri in seen_uris:
                continue
            seen_uris.add(entity_uri)

            vertex = vertex_map.get(entity_uri)
            if vertex is None:
                node_data = unified_graph.nodes.get(entity_uri, {})
                entity_name = str(node_data.get("name", entity_uri))
                entity_type = str(node_data.get("entity_type", ""))
            else:
                entity_name = str(vertex.get("name", entity_uri))
                entity_type = str(vertex.get("entity_type", ""))

            # Boost by connected edge strength
            connected_edges = edges_by_name.get(entity_name, [])
            connected_strength = 0.0
            for edge in connected_edges:
                if edge.connection_strength is not None:
                    connected_strength = max(connected_strength, edge.connection_strength)

            final_score: float
            if connected_strength > 0:
                final_score = pr_score * (1 + 0.2 * connected_strength)
            else:
                final_score = pr_score

            graph_results.append(
                GraphSearchResult(
                    entity_uri=entity_uri,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    score=final_score,
                ),
            )

        graph_results.sort(key=lambda x: x.score, reverse=True)
        return graph_results[:topn]

    async def _get_entity_documents(
        self,
        entity_uri: str,
        session,
    ) -> list[UUID]:
        stmt = select(col(DocumentTable.id)).where(col(DocumentTable.entities).contains([entity_uri]))
        result = await session.execute(stmt)
        return [row[0] for row in result.fetchall()]

    @staticmethod
    def _rrf_fusion(
        vector_results: list[UUID],
        bm25_results: list[UUID],
        graph_results: list[tuple[UUID, float]] | None = None,
        topk: int = 10,
        rrf_k: int = 60,
        graph_weight: float = 0.3,
        vector_weight: float = 0.4,
        bm25_weight: float = 0.3,
    ) -> list[UUID]:
        rrf_scores: dict[UUID, float] = {}

        for rank, doc_id in enumerate(vector_results, start=1):
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
            rrf_scores[doc_id] += (1.0 / (rrf_k + rank)) * vector_weight

        for rank, doc_id in enumerate(bm25_results, start=1):
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
            rrf_scores[doc_id] += (1.0 / (rrf_k + rank)) * bm25_weight

        if graph_results:
            doc_ranks: dict[UUID, int] = {}
            for rank, (doc_id, _) in enumerate(graph_results, start=1):
                if doc_id not in doc_ranks:
                    doc_ranks[doc_id] = rank
            for doc_id, rank in doc_ranks.items():
                if doc_id not in rrf_scores:
                    rrf_scores[doc_id] = 0.0
                rrf_scores[doc_id] += (1.0 / (rrf_k + rank)) * graph_weight

        sorted_rrf_results = sorted(rrf_scores.items(), key=operator.itemgetter(1), reverse=True)[:topk]
        return [doc_id for doc_id, _ in sorted_rrf_results]

    async def ahyprid_search(
        self,
        queries: list[str],
        k: int = 4,
        rag_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
        use_graph: bool = False,
        max_hops: int = 3,
        graph_weight: float = 0.3,
        vector_weight: float = 0.4,
        bm25_weight: float = 0.3,
    ) -> tuple[list[Document], list[GraphSearchResult]]:
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

            graph_entities: list[GraphSearchResult] = []
            graph_search_results: list[tuple[UUID, float]] | None = None
            if use_graph:
                all_search_doc_ids = list(set(vector_results + bm25_results))
                entity_stats = await self._collect_entity_uris(all_search_doc_ids, session)

                graph_entities = await self._graph_search(
                    queries=queries,
                    topn=topn,
                    entity_uris_with_scores=entity_stats,
                    max_hops=max_hops,
                    session=session,
                )
                if graph_entities:
                    graph_doc_ids: list[tuple[UUID, float]] = []
                    for gsr in graph_entities:
                        doc_ids = await self._get_entity_documents(gsr.entity_uri, session)
                        for doc_id in doc_ids:
                            graph_doc_ids.append((doc_id, gsr.score))
                    graph_doc_ids.sort(key=operator.itemgetter(1), reverse=True)
                    graph_search_results = graph_doc_ids[:topn]

            doc_ids = self._rrf_fusion(
                vector_results=vector_results,
                bm25_results=bm25_results,
                graph_results=graph_search_results,
                topk=topk,
                rrf_k=rrf_k,
                graph_weight=graph_weight,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
            )

            if not doc_ids:
                return [], graph_entities

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
            return documents[:k], graph_entities

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
        use_graph: bool = False,
        max_hops: int = 3,
        graph_weight: float = 0.3,
        vector_weight: float = 0.4,
        bm25_weight: float = 0.3,
    ) -> list[QueryDocumentResult]:
        conf = await RAGConfig().aget(rag_id)
        assert conf is not None, "知识库不存在"

        results, _ = await self.ahyprid_search(
            queries,
            k=5,
            rag_id=rag_id,
            regex=regex,
            file_ids=file_ids,
            use_graph=use_graph,
            max_hops=max_hops,
            graph_weight=graph_weight,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
        )

        return [
            QueryDocumentResult(
                content=result.content,
                source_name=result.source_name or "untitled",
                score=result.query_score if result.query_score is not None else float("nan"),
            )
            for result in results
        ]

    async def aquery_graph_context(
        self,
        queries: list[str],
        max_hops: int = 3,
    ) -> dict:
        async with self.__db.asession() as session:
            doc_ids = await self._vector_search(queries=queries, topn=30, session=session)
            entity_stats = await self._collect_entity_uris(doc_ids, session)

            graph_entities = await self._graph_search(
                queries=queries,
                topn=10,
                entity_uris_with_scores=entity_stats,
                max_hops=max_hops,
                session=session,
            )

        context = {
            "entities": [],
            "paths": [],
            "relationships": [],
        }

        for gsr in graph_entities:
            context["entities"].append(
                {
                    "uri": gsr.entity_uri,
                    "name": gsr.entity_name,
                    "type": gsr.entity_type,
                    "score": gsr.score,
                },
            )
            if gsr.path:
                for node_uri, data in gsr.path.nodes(data=True):
                    context["paths"].append(
                        {
                            "uri": node_uri,
                            "name": data.get("name"),
                            "type": data.get("entity_type"),
                        },
                    )

        return context

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
