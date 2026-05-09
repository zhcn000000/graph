import operator
from collections import Counter
from typing import NamedTuple
from uuid import UUID

from networkx import DiGraph, ego_graph, pagerank
from sqlalchemy import Float, cast, func, select
from sqlmodel import col

from knowgraph.documents.embedder import aembed_documents, arerank_documents
from knowgraph.documents.models import Document
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.graph.edge_strength import TripleBasedEdgeQuerier

from .database import DatabaseManager
from .graph import AgeGraphManager
from .tables import DocumentTable, Source
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


class RAGMode:
    def __init__(self, dbname: str | None = None) -> None:
        self.__db = DatabaseManager(dbname)
        self._graph_manager: AgeGraphManager | None = None
        self._edge_querier: TripleBasedEdgeQuerier | None = None

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

    @staticmethod
    async def _vector_search(
        queries: list[str],
        topn: int,
        session,
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
    ) -> list[UUID]:
        query_vector = await aembed_documents(queries)

        vector_stmt = select(col(DocumentTable.id))
        if file_ids:
            vector_stmt = vector_stmt.join(Source, col(DocumentTable.file_id) == col(Source.id))
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
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
    ) -> list[UUID]:
        query_count = Counter()
        for q in queries:
            query_count += await atokenize_content(q)

        bm25_stmt = select(col(DocumentTable.id))
        if file_ids:
            bm25_stmt = bm25_stmt.join(Source, col(DocumentTable.file_id) == col(Source.id))
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
    ) -> list[GraphSearchResult]:
        if not entity_uris_with_scores:
            return []

        entity_score_map: dict[str, float] = dict(entity_uris_with_scores)

        scan_uris = [uri for uri, _ in entity_uris_with_scores[: max(topn * 3, 30)]]
        vertex_rows = await self.graph_manager.aget_vertices_by_uris(scan_uris)
        vertex_map: dict[str, dict[str, object]] = {r["uri"]: r for r in vertex_rows}

        unified_graph = DiGraph()
        traverse_uris = [uri for uri, _ in entity_uris_with_scores[: max(topn * 2, 20)] if uri in vertex_map]
        if traverse_uris:
            unified_graph = await self.graph_manager.atraverse_multi(traverse_uris, max_hops=max_hops)

        if unified_graph.number_of_nodes() == 0:
            return []

        uri_to_node_key: dict[str, object] = {}
        for node_key in unified_graph.nodes():
            node_uri = unified_graph.nodes[node_key].get("uri", "")
            if node_uri:
                uri_to_node_key[node_uri] = node_key

        personalization: dict[str, float] = {}
        for node_key in unified_graph.nodes():
            node_uri = unified_graph.nodes[node_key].get("uri", "")
            personalization[node_key] = entity_score_map.get(node_uri, 0.0)

        total_pers = sum(personalization.values())
        if total_pers > 0:
            pr_scores = pagerank(unified_graph, personalization=personalization)
        else:
            pr_scores = pagerank(unified_graph)

        names: list[str] = [
            str(vertex_map[uri]["name"])
            for uri in entity_score_map
            if uri in vertex_map and vertex_map[uri].get("name")
        ][:30]

        edges_by_name = await self.edge_querier.query_edges_by_entity_names(names)

        graph_results: list[GraphSearchResult] = []
        seen_uris: set[str] = set()

        sorted_by_pr = sorted(pr_scores.items(), key=operator.itemgetter(1), reverse=True)

        for node_key, pr_score in sorted_by_pr:
            node_data = unified_graph.nodes.get(node_key, {})
            entity_uri = str(node_data.get("uri", ""))
            if not entity_uri or entity_uri in seen_uris:
                continue
            seen_uris.add(entity_uri)

            vertex = vertex_map.get(entity_uri)
            if vertex is None:
                entity_name = str(node_data.get("name", str(node_key)))
                entity_type = str(node_data.get("entity_type", ""))
            else:
                entity_name = str(vertex.get("name", entity_uri))
                entity_type = str(vertex.get("entity_type", ""))

            connected_edges = edges_by_name.get(entity_name, [])
            connected_strength = 0.0
            for edge in connected_edges:
                if edge.predicate.strength is not None:
                    connected_strength = max(connected_strength, edge.predicate.strength)

            final_score: float
            if connected_strength > 0:
                final_score = pr_score * (1 + 0.2 * connected_strength)
            else:
                final_score = pr_score

            path_graph: DiGraph | None = None
            entity_node_key = uri_to_node_key.get(entity_uri)
            if entity_node_key is not None:
                path_graph = ego_graph(unified_graph, entity_node_key, radius=max_hops, undirected=True)

            graph_results.append(
                GraphSearchResult(
                    entity_uri=entity_uri,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    score=final_score,
                    path=path_graph,
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
        file_ids: list[UUID] | None = None,
        regex: str | None = None,
        use_graph: bool = False,
        max_hops: int = 3,
        graph_weight: float = 0.3,
        vector_weight: float = 0.4,
        bm25_weight: float = 0.3,
        offset: int = 0,
    ) -> tuple[list[Document], list[GraphSearchResult]]:
        topn = k * 5
        topk = k * 3
        rrf_k = 60

        async with self.__db.asession() as session:
            vector_results = await self._vector_search(
                queries=queries,
                topn=topn,
                session=session,
                file_ids=file_ids,
                regex=regex,
            )

            bm25_results = await self._bm25_search(
                queries=queries,
                topn=topn,
                session=session,
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
                    col(Source.name),
                    col(Source.link),
                    col(DocumentTable.document_index),
                    col(DocumentTable.chunk_index),
                )
                .join(Source, col(Source.id) == col(DocumentTable.file_id))
                .where(col(DocumentTable.id).in_(doc_ids))
            )

            doc_result = await session.execute(doc_stmt)
            docs = {row[0]: row for row in doc_result.fetchall()}

            ordered_docs = [docs[doc_id] for doc_id in doc_ids if doc_id in docs]

            documents = [
                Document(
                    id=row[0],
                    content=row[1],
                    metadata=row[2] or {},
                    name=row[3],
                    link=row[4],
                    document_index=row[5],
                    chunk_index=row[6],
                )
                for row in ordered_docs
            ]

            documents = await arerank_documents("\n".join(queries), documents)
            return documents[offset : offset + k], graph_entities

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
                        name=meta.get("file_name"),
                        link=meta.get("file_hash"),
                        metadata=meta,
                    ),
                )
            return documents

    async def aquery_documents(
        self,
        queries: list[str],
        regex: str | None = None,
        file_ids: list[UUID] | None = None,
        use_graph: bool = False,
        max_hops: int = 3,
        graph_weight: float = 0.3,
        vector_weight: float = 0.4,
        bm25_weight: float = 0.3,
    ) -> list[QueryDocumentResult]:
        results, _ = await self.ahyprid_search(
            queries,
            k=5,
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
                source_name=result.name or "untitled",
                score=result.query_score if result.query_score is not None else 0.0,
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
            )

        context = {
            "entities": [],
            "paths": [],
            "relationships": [],
        }

        seen_path_nodes: set[str] = set()
        seen_relationships: set[tuple[str, str, str | None]] = set()

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
                for node_key, data in gsr.path.nodes(data=True):
                    node_uri = str(data.get("uri", node_key))
                    if node_uri in seen_path_nodes:
                        continue
                    seen_path_nodes.add(node_uri)
                    context["paths"].append(
                        {
                            "uri": node_uri,
                            "name": data.get("name"),
                            "type": data.get("entity_type"),
                        },
                    )

                for u, v, data in gsr.path.edges(data=True):
                    start_uri = str(gsr.path.nodes[u].get("uri", u))
                    end_uri = str(gsr.path.nodes[v].get("uri", v))
                    rel = data.get("label")
                    rel_key = (start_uri, end_uri, rel)
                    if rel_key in seen_relationships:
                        continue
                    seen_relationships.add(rel_key)
                    context["relationships"].append(
                        {
                            "start_uri": start_uri,
                            "end_uri": end_uri,
                            "relationship": rel,
                        },
                    )

        return context

    async def aget_document_context(
        self,
        document_index: int,
        chunk_index: int | None = None,
        before: int = 1,
        after: int = 1,
    ) -> dict:
        async with self.__db.asession() as session:
            stmt = (
                select(
                    col(DocumentTable.id),
                    col(DocumentTable.content),
                    col(DocumentTable.chunk_index),
                    col(DocumentTable.document_index),
                    col(DocumentTable.entities),
                )
                .where(
                    col(DocumentTable.document_index) == document_index,
                )
                .order_by(col(DocumentTable.chunk_index))
            )

            result = await session.execute(stmt)
            rows = result.fetchall()

        chunks = [
            {
                "id": str(row[0]),
                "content": row[1],
                "chunk_index": row[2],
                "document_index": row[3],
                "entities": row[4] or [],
            }
            for row in rows
        ]

        if chunk_index is not None:
            lo = max(0, chunk_index - before)
            hi = min(len(chunks), chunk_index + after + 1)
            context_chunks: list[dict] = []
            for c in chunks:
                ci = c["chunk_index"]
                if isinstance(ci, int) and lo <= ci <= hi:
                    context_chunks.append(c)
        else:
            context_chunks = chunks

        return {
            "document_index": document_index,
            "total_chunks": len(chunks),
            "chunks": context_chunks,
        }

    async def aget_document_entities(
        self,
        document_index: int,
    ) -> dict:
        async with self.__db.asession() as session:
            stmt = select(col(DocumentTable.entities)).where(
                col(DocumentTable.document_index) == document_index,
            )
            result = await session.execute(stmt)
            all_entities: set[str] = set()
            for row in result.fetchall():
                if row[0]:
                    all_entities.update(row[0])

            entity_details: list[dict] = []
            if all_entities:
                vertices = await self.graph_manager.aget_vertices_by_uris(list(all_entities))
                vertex_map_batch = {v["uri"]: v for v in vertices}
                for uri in all_entities:
                    vertex = vertex_map_batch.get(uri)
                    if vertex:
                        entity_details.append({
                            "uri": uri,
                            "name": vertex.get("name", uri),
                            "entity_type": vertex.get("entity_type", ""),
                        })

        return {
            "document_index": document_index,
            "entities": entity_details,
        }
