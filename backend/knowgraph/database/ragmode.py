import operator
from collections import Counter
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Float, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from knowgraph.documents.converter import aload_documents
from knowgraph.documents.embedder import aembed_documents, arerank_documents
from knowgraph.documents.models import Document
from knowgraph.documents.splitter import asplit_content, asplit_documents
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.graph.edge_strength import EdgeStrengthCalculator, TripleBasedEdgeQuerier
from knowgraph.graph.triples import LLMExtractor
from knowgraph.utils.file import FileStream

from .database import DatabaseManager
from .document import DocumentStore
from .graph import AgeGraphManager, GraphPath
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
    path: GraphPath | None = None


class GraphRAGConfig:
    GRAPH_WEIGHT: float = 0.3
    VECTOR_WEIGHT: float = 0.4
    BM25_WEIGHT: float = 0.3
    MAX_HOPS: int = 3
    GRAPH_TOP_K: int = 50
    EDGE_STRENGTH_BOOST: float = 0.2
    EDGE_STRENGTH_WEIGHT: float = 0.15


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
        all_doc_ids = []

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
                    await self.graph_manager.acreate_vertex(
                        subject_label,
                        {
                            "uri": triple.subject.uri,
                            "name": triple.subject.name,
                            "entity_type": triple.subject.entity_type.value,
                        },
                    )
                    await self.graph_manager.acreate_vertex(
                        object_label,
                        {
                            "uri": triple.object.uri,
                            "name": triple.object.name,
                            "entity_type": triple.object.entity_type.value,
                        },
                    )
                    await self.graph_manager.acreate_edge(
                        triple.subject.uri,
                        triple.object.uri,
                        triple.predicate.value,
                        start_label=subject_label,
                        end_label=object_label,
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
        max_hops: int = 2,
        graph_config: GraphRAGConfig | None = None,
        session=None,
    ) -> list[GraphSearchResult]:
        if graph_config is None:
            graph_config = GraphRAGConfig()

        # Step 1: Find relevant entities via vector search on documents
        if session is not None:
            doc_ids = await self._vector_search(
                queries=queries,
                topn=max(topn * 3, 20),
                session=session,
            )
            entity_stats = await self._collect_entity_uris(doc_ids, session)
        else:
            async with self.__db.asession() as sess:
                doc_ids = await self._vector_search(
                    queries=queries,
                    topn=max(topn * 3, 20),
                    session=sess,
                )
                entity_stats = await self._collect_entity_uris(doc_ids, sess)

        if not entity_stats:
            return []

        top_entities = entity_stats[: max(topn * 3, 30)]

        # Step 2: Batch lookup all vertices at once
        uris = [uri for uri, _ in top_entities]
        vertex_cypher = """
        UNWIND $uris as uri
        MATCH (v {uri: uri})
        RETURN v.uri as uri, id(v) as id, v.name as name, v.entity_type as entity_type
        """
        vertex_rows = await self.graph_manager._execute_cypher(vertex_cypher, {"uris": uris})
        vertex_map: dict[str, dict[str, object]] = {r["uri"]: r for r in vertex_rows}

        # Step 3: Batch lookup adjacent edges using entity names
        names = [r["name"] for r in vertex_map.values() if r.get("name")]
        from collections import defaultdict

        edges_by_name: dict[str, list[EdgeConnectionInfo]] = defaultdict(list)
        if names:
            from knowgraph.graph.edge_strength import EdgeConnectionInfo

            edge_cypher = """
            UNWIND $names as name
            MATCH (s)-[r]->(o)
            WHERE startNode(r).name CONTAINS name
            RETURN name as query_name, type(r) as relationship_type,
                   startNode(r).uri as start_node_uri, startNode(r).name as subject_name,
                   endNode(r).uri as end_node_uri, endNode(r).name as object_name,
                   r.description as description, r.connection_strength as connection_strength
            LIMIT 500
            UNION ALL
            UNWIND $names as name
            MATCH (s)-[r]->(o)
            WHERE endNode(r).name CONTAINS name
            RETURN name as query_name, type(r) as relationship_type,
                   startNode(r).uri as start_node_uri, startNode(r).name as subject_name,
                   endNode(r).uri as end_node_uri, endNode(r).name as object_name,
                   r.description as description, r.connection_strength as connection_strength
            LIMIT 500
            """
            edge_rows = await self.graph_manager._execute_cypher(edge_cypher, {"names": names})
            for row in edge_rows:
                query_name = row["query_name"]
                if len(edges_by_name[query_name]) >= 20:
                    continue
                predicate_desc = row.get("relationship_type", "").replace("_", " ")
                edges_by_name[query_name].append(
                    EdgeConnectionInfo(
                        start_node_uri=row.get("start_node_uri", ""),
                        end_node_uri=row.get("end_node_uri", ""),
                        relationship_type=row.get("relationship_type", ""),
                        subject_name=row.get("subject_name", ""),
                        object_name=row.get("object_name", ""),
                        description=row.get("description"),
                        predicate_description=predicate_desc,
                        connection_strength=row.get("connection_strength"),
                    ),
                )

        # Step 4: Re-rank edges dynamically against current query
        combined_query = " ".join(queries)
        all_edges: list[EdgeConnectionInfo] = []
        for edges in edges_by_name.values():
            all_edges.extend(edges)
        if all_edges:
            await self.edge_calculator.compute_strength_for_edges(combined_query, all_edges)

        # Step 5: Build results with per-entity traversal
        graph_results: list[GraphSearchResult] = []
        seen_uris: set[str] = set()

        for entity_uri, relevance in top_entities:
            if entity_uri in seen_uris:
                continue
            seen_uris.add(entity_uri)

            vertex = vertex_map.get(entity_uri)
            if vertex is None or not vertex.get("name"):
                continue

            entity_name = str(vertex["name"])
            connected_edges = edges_by_name.get(entity_name, [])

            connected_strength = 0.0
            for edge in connected_edges:
                if edge.connection_strength is not None:
                    connected_strength = max(connected_strength, edge.connection_strength)

            if connected_strength > 0:
                final_score = relevance * (1 + graph_config.EDGE_STRENGTH_BOOST * connected_strength)
            else:
                final_score = relevance

            path = await self.graph_manager.atraverse(entity_uri, max_hops=max_hops)
            graph_results.append(
                GraphSearchResult(
                    entity_uri=entity_uri,
                    entity_name=entity_name,
                    entity_type=str(vertex.get("entity_type", "")),
                    score=final_score,
                    path=path,
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
        graph_config: GraphRAGConfig | None = None,
    ) -> tuple[list[Document], list[GraphSearchResult]]:
        topn = k * 5
        topk = k * 3
        rrf_k = 60

        if graph_config is None:
            graph_config = GraphRAGConfig()

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
                graph_entities = await self._graph_search(
                    queries=queries,
                    topn=graph_config.GRAPH_TOP_K,
                    max_hops=graph_config.MAX_HOPS,
                    graph_config=graph_config,
                    session=session,
                )
                if graph_entities:
                    graph_doc_ids: list[tuple[UUID, float]] = []
                    for gsr in graph_entities:
                        doc_ids = await self._get_entity_documents(gsr.entity_uri, session)
                        for doc_id in doc_ids:
                            graph_doc_ids.append((doc_id, gsr.score))
                    graph_search_results = graph_doc_ids

            doc_ids = self._rrf_fusion(
                vector_results=vector_results,
                bm25_results=bm25_results,
                graph_results=graph_search_results,
                topk=topk,
                rrf_k=rrf_k,
                graph_weight=graph_config.GRAPH_WEIGHT,
                vector_weight=graph_config.VECTOR_WEIGHT,
                bm25_weight=graph_config.BM25_WEIGHT,
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
        graph_entities = await self._graph_search(
            queries=queries,
            topn=10,
            max_hops=max_hops,
            graph_config=GraphRAGConfig(),
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
                for node in gsr.path.nodes:
                    context["paths"].append(
                        {
                            "uri": node.uri,
                            "name": node.name,
                            "type": node.entity_type,
                        },
                    )

        return context

    async def aexpand_context_by_graph(
        self,
        entity_uri: str,
        max_hops: int = 2,
        direction: str = "both",
    ) -> dict:
        path = await self.graph_manager.atraverse(entity_uri, max_hops=max_hops, direction=direction)

        context = {
            "center_entity": entity_uri,
            "connected_entities": [],
            "paths": [],
        }

        for node in path.nodes:
            if node.uri != entity_uri:
                context["connected_entities"].append(
                    {
                        "uri": node.uri,
                        "name": node.name,
                        "type": node.entity_type,
                    },
                )

        for edge in path.edges:
            context["paths"].append(
                {
                    "start_uri": edge.start_node_uri,
                    "end_uri": edge.end_node_uri,
                    "relationship": edge.relationship_type,
                },
            )

        return context

    async def aget_entity_paths(
        self,
        start_uri: str,
        end_uri: str,
        max_hops: int = 5,
    ) -> list[dict]:
        paths = await self.graph_manager.afind_paths(start_uri, end_uri, max_hops)

        result = []
        for path in paths:
            path_dict = {"nodes": [], "edges": []}
            for node in path.nodes:
                path_dict["nodes"].append(
                    {
                        "uri": node.uri,
                        "name": node.name,
                        "type": node.entity_type,
                    },
                )
            for edge in path.edges:
                path_dict["edges"].append(
                    {
                        "start_uri": edge.start_node_uri,
                        "end_uri": edge.end_node_uri,
                        "relationship": edge.relationship_type,
                    },
                )
            result.append(path_dict)

        return result

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
