import logging
import operator
from collections import Counter
from typing import NamedTuple
from uuid import UUID

from asyncer import create_task_group
from networkx import DiGraph, ego_graph, pagerank
from sqlalchemy import Float, cast, func, select
from sqlmodel import col

from knowgraph.documents.embedder import aembed_documents, arerank_documents
from knowgraph.documents.models import Document
from knowgraph.documents.tokenizer import atokenize_document
from knowgraph.graph.schema import EntityType, ExtractedEntity

from .database import DatabaseManager
from .graph import AgeGraphManager
from .tables import DocumentTable, Source
from .types import BM25Vector


def _merge_graphs(graph_a: DiGraph, graph_b: DiGraph) -> DiGraph:
    for node, data in graph_b.nodes(data=True):
        if node not in graph_a:
            graph_a.add_node(node, **data)
    for u, v, data in graph_b.edges(data=True):
        if not graph_a.has_edge(u, v):
            graph_a.add_edge(u, v, **data)
    return graph_a


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

    @property
    def graph_manager(self) -> AgeGraphManager:
        if self._graph_manager is None:
            self._graph_manager = AgeGraphManager(dbname=self.__db.dbname)
        return self._graph_manager

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
            query_count += await atokenize_document(q)

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

    @staticmethod
    async def _collect_entity_uris(
        doc_ids: list[UUID],
        session,
        max_entities: int = 500,
    ) -> list[str]:
        if not doc_ids:
            return []
        stmt = select(col(DocumentTable.entities)).where(col(DocumentTable.id).in_(doc_ids))
        result = await session.execute(stmt)
        counter: dict[str, int] = {}
        for row in result.fetchall():
            entities = row[0] or []
            for uri in entities:
                counter[uri] = counter.get(uri, 0) + 1

        ranked = sorted(counter.items(), key=operator.itemgetter(1), reverse=True)
        return [uri for uri, _ in ranked[:max_entities]]

    async def _graph_pagerank(
        self,
        entity_uris: list[str],
        max_hops: int = 2,
        max_results: int | None = None,
    ) -> list[GraphSearchResult]:
        if not entity_uris:
            return []

        vertex_rows = await self.graph_manager.aget_vertices_by_uris(entity_uris)
        logging.debug(f"Fetched {len(vertex_rows)} vertices for PageRank computation")
        vertex_map: dict[str, dict[str, object]] = {}
        for r in vertex_rows:
            entity_type = str(r.get("entity_type", ""))
            name = str(r.get("name", ""))
            if entity_type and name:
                computed_uri = str(ExtractedEntity(name=name, entity_type=EntityType(entity_type)).uri)
                r["uri"] = computed_uri
                vertex_map[computed_uri] = r

        unified_graph = DiGraph()
        traverse_uris = [uri for uri in entity_uris if uri in vertex_map]
        batch_size = 10
        for i in range(0, len(traverse_uris), batch_size):
            batch = traverse_uris[i : i + batch_size]
            logging.debug(
                f"Traversing batch {i // batch_size + 1}/{(len(traverse_uris) + batch_size - 1) // batch_size}"
                f" with {len(batch)} start URIs (max_hops={max_hops})"
            )
            batch_graph = await self.graph_manager.atraverse_multi(batch, max_hops=max_hops)
            unified_graph = _merge_graphs(unified_graph, batch_graph)
        logging.debug(
            f"Constructed unified graph with {unified_graph.number_of_nodes()} nodes"
            f" and {unified_graph.number_of_edges()} edges"
        )

        if unified_graph.number_of_nodes() == 0:
            return []

        for _, __, data in unified_graph.edges(data=True):
            props = data.get("properties", {})
            if not isinstance(props, dict):
                data["weight"] = 0.01
                continue
            cs = props.get("connection_strength")
            if cs is not None:
                data["weight"] = float(cs)
            else:
                data["weight"] = 0.01

        uri_to_node_key: dict[str, object] = {}
        for node_key in unified_graph.nodes():
            data = unified_graph.nodes[node_key]
            node_props = data.get("properties", {}) if isinstance(data.get("properties"), dict) else {}
            entity_type = str(data.get("entity_type") or node_props.get("entity_type", ""))
            name = str(data.get("name") or node_props.get("name", ""))
            if entity_type and name:
                node_uri = str(ExtractedEntity(name=name, entity_type=EntityType(entity_type)).uri)
            else:
                node_uri = str(data.get("uri", str(node_key)))
            if node_uri:
                uri_to_node_key[node_uri] = node_key

        pr_scores = pagerank(unified_graph, weight="weight")

        scored_entities: list[tuple[str, str, str, float, object | None]] = []
        seen_uris: set[str] = set()

        sorted_by_pr = sorted(pr_scores.items(), key=operator.itemgetter(1), reverse=True)

        for node_key, pr_score in sorted_by_pr:
            node_data = unified_graph.nodes.get(node_key, {})
            node_props = node_data.get("properties", {}) if isinstance(node_data.get("properties"), dict) else {}
            node_entity_type = str(node_data.get("entity_type") or node_props.get("entity_type", ""))
            node_name = str(node_data.get("name") or node_props.get("name", ""))
            if node_entity_type and node_name:
                entity_uri = str(ExtractedEntity(name=node_name, entity_type=EntityType(node_entity_type)).uri)
            else:
                entity_uri = str(node_data.get("uri", str(node_key)))
            if not entity_uri or entity_uri in seen_uris:
                continue
            seen_uris.add(entity_uri)

            vertex = vertex_map.get(entity_uri)
            if vertex is None:
                entity_name = str(node_data.get("name") or node_props.get("name", str(node_key)))
                entity_type = str(node_data.get("entity_type") or node_props.get("entity_type", ""))
            else:
                entity_name = str(vertex.get("name", entity_uri))
                entity_type = str(vertex.get("entity_type", ""))

            entity_node_key = uri_to_node_key.get(entity_uri)
            scored_entities.append(
                (entity_uri, entity_name, entity_type, pr_score, entity_node_key),
            )

        scored_entities.sort(key=operator.itemgetter(3), reverse=True)

        ego_graph_limit = max_results if max_results is not None else len(scored_entities)

        graph_results: list[GraphSearchResult] = []
        for idx, (entity_uri, entity_name, entity_type, score, entity_node_key) in enumerate(scored_entities):
            path_graph: DiGraph | None = None
            if idx < ego_graph_limit and entity_node_key is not None:
                path_graph = ego_graph(unified_graph, entity_node_key, radius=max_hops, undirected=True)

            graph_results.append(
                GraphSearchResult(
                    entity_uri=entity_uri,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    score=score,
                    path=path_graph,
                ),
            )

        return graph_results

    async def _graph_search(
        self,
        topn: int,
        entity_uris: list[str],
        session,
        max_hops: int = 2,
    ) -> tuple[list[UUID], list[GraphSearchResult]]:
        graph_entities = await self._graph_pagerank(
            entity_uris=entity_uris,
            max_hops=max_hops,
            max_results=topn,
        )
        logging.info(f"Graph PageRank identified {len(graph_entities)} relevant entities for graph search")

        if not graph_entities:
            return [], []

        max_graph_entities = topn * 10
        all_entity_uris = [gsr.entity_uri for gsr in graph_entities[:max_graph_entities]]

        if not all_entity_uris:
            return [], []

        stmt = select(col(DocumentTable.id), col(DocumentTable.entities)).where(
            col(DocumentTable.entities).op("&&")(all_entity_uris),
        )
        result = await session.execute(stmt)
        rows = result.fetchall()

        entity_rank: dict[str, int] = {uri: idx for idx, uri in enumerate(all_entity_uris)}

        doc_pairs: list[tuple[UUID, int]] = []
        for row in rows:
            doc_id, doc_entities = row[0], row[1] or []
            best_rank = min(
                (entity_rank.get(e, len(all_entity_uris)) for e in doc_entities),
                default=len(all_entity_uris),
            )
            doc_pairs.append((doc_id, best_rank))

        doc_pairs.sort(key=operator.itemgetter(1))

        seen: set[UUID] = set()
        doc_ids: list[UUID] = []
        for doc_id, _ in doc_pairs:
            if doc_id not in seen:
                seen.add(doc_id)
                doc_ids.append(doc_id)

        return doc_ids[:topn], graph_entities[:topn]

    @staticmethod
    def _rrf_fusion(
        vector_results: list[UUID],
        bm25_results: list[UUID],
        graph_results: list[UUID] | None = None,
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
            for rank, doc_id in enumerate(graph_results, start=1):
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
        use_graph: bool = True,
        max_hops: int = 2,
        graph_weight: float = 0.3,
        vector_weight: float = 0.4,
        bm25_weight: float = 0.3,
        offset: int = 0,
    ) -> tuple[list[Document], list[GraphSearchResult]]:
        topn = k * 5
        topk = k * 3
        rrf_k = 60

        async with self.__db.asession() as session:
            async with create_task_group() as tg:
                vector_task = tg.soonify(self._vector_search)(
                    queries=queries,
                    topn=topn,
                    session=session,
                    file_ids=file_ids,
                    regex=regex,
                )

                bm25_task = tg.soonify(self._bm25_search)(
                    queries=queries,
                    topn=topn,
                    session=session,
                    file_ids=file_ids,
                    regex=regex,
                )

            vector_results = vector_task.value
            bm25_results = bm25_task.value
            logging.info(f"Vector search returned {len(vector_results)} results")
            logging.info(f"BM25 search returned {len(bm25_results)} results")
            graph_entities: list[GraphSearchResult] = []
            graph_results: list[UUID] | None = None
            if use_graph:
                all_search_doc_ids = list(set(vector_results + bm25_results))
                entity_stats = await self._collect_entity_uris(all_search_doc_ids, session)
                logging.debug(f"Collected {len(entity_stats)} unique entity URIs from top search results")

                graph_results, graph_entities = await self._graph_search(
                    topn=topn,
                    entity_uris=entity_stats,
                    session=session,
                    max_hops=max_hops,
                )
                logging.info(
                    f"Graph search returned {len(graph_results)} document results "
                    f"and {len(graph_entities)} graph entities"
                )

            doc_ids = self._rrf_fusion(
                vector_results=vector_results,
                bm25_results=bm25_results,
                graph_results=graph_results,
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
            stmt = (
                select(
                    col(DocumentTable.id),
                    col(DocumentTable.content),
                    col(DocumentTable.meta),
                    col(DocumentTable.document_index),
                    col(DocumentTable.chunk_index),
                    col(DocumentTable.entities),
                    col(Source.name),
                    col(Source.link),
                )
                .join(Source, col(Source.id) == col(DocumentTable.file_id))
                .where(col(DocumentTable.id).in_(uid_list))
            )
            result = await session.execute(stmt)
            for row in result.all():
                documents.append(
                    Document(
                        id=row[0],
                        content=row[1],
                        metadata=row[2] or {},
                        document_index=row[3],
                        chunk_index=row[4],
                        entities=row[5] or [],
                        name=row[6],
                        link=row[7],
                    ),
                )
            return documents

    async def aquery_documents(
        self,
        queries: list[str],
        regex: str | None = None,
        file_ids: list[UUID] | None = None,
        use_graph: bool = False,
        max_hops: int = 2,
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
        max_hops: int = 2,
    ) -> dict:
        async with self.__db.asession() as session:
            doc_ids = await self._vector_search(queries=queries, topn=30, session=session)
            entity_stats = await self._collect_entity_uris(doc_ids, session)

            graph_entities = await self._graph_pagerank(
                entity_uris=entity_stats,
                max_hops=max_hops,
                max_results=10,
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
                    node_props = data.get("properties", {}) if isinstance(data.get("properties"), dict) else {}
                    entity_type = str(data.get("entity_type") or node_props.get("entity_type", ""))
                    name = str(data.get("name") or node_props.get("name", ""))
                    if entity_type and name:
                        node_uri = str(ExtractedEntity(name=name, entity_type=EntityType(entity_type)).uri)
                    else:
                        node_uri = str(node_key)
                    if node_uri in seen_path_nodes:
                        continue
                    seen_path_nodes.add(node_uri)
                    context["paths"].append(
                        {
                            "uri": node_uri,
                            "name": data.get("name") or node_props.get("name"),
                            "type": data.get("entity_type") or node_props.get("entity_type"),
                        },
                    )

                for u, v, data in gsr.path.edges(data=True):
                    start_data = gsr.path.nodes[u]
                    end_data = gsr.path.nodes[v]
                    start_np = (
                        start_data.get("properties", {}) if isinstance(start_data.get("properties"), dict) else {}
                    )
                    end_np = end_data.get("properties", {}) if isinstance(end_data.get("properties"), dict) else {}
                    start_et = str(start_data.get("entity_type") or start_np.get("entity_type", ""))
                    start_n = str(start_data.get("name") or start_np.get("name", ""))
                    end_et = str(end_data.get("entity_type") or end_np.get("entity_type", ""))
                    end_n = str(end_data.get("name") or end_np.get("name", ""))
                    if start_et and start_n:
                        start_uri = str(ExtractedEntity(name=start_n, entity_type=EntityType(start_et)).uri)
                    else:
                        start_uri = str(u)
                    if end_et and end_n:
                        end_uri = str(ExtractedEntity(name=end_n, entity_type=EntityType(end_et)).uri)
                    else:
                        end_uri = str(v)
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
                vertex_map_batch: dict[str, dict] = {}
                for v in vertices:
                    vt = str(v.get("entity_type", ""))
                    vn = str(v.get("name", ""))
                    if vt and vn:
                        computed_uri = str(ExtractedEntity(name=vn, entity_type=EntityType(vt)).uri)
                        vertex_map_batch[computed_uri] = v
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

    async def acheck_similar_documents(
        self,
        content: str,
        threshold: float = 0.95,
        topn: int = 5,
    ) -> list[dict]:
        async with self.__db.asession() as session:
            query_vector = await aembed_documents([content])
            stmt = (
                select(
                    col(DocumentTable.id),
                    col(DocumentTable.content),
                    col(DocumentTable.file_id),
                    col(DocumentTable.vector).op("@#", return_type=Float)(query_vector).label("similarity"),
                )
                .order_by(col("similarity").desc())
                .limit(topn * 2)
            )
            result = await session.execute(stmt)
            rows = result.fetchall()

        if not rows:
            return []

        file_ids = list({row[2] for row in rows if row[2]})
        source_map: dict[UUID, str] = {}
        if file_ids:
            async with self.__db.asession() as session:
                src_stmt = select(col(Source.id), col(Source.name)).where(col(Source.id).in_(file_ids))
                src_result = await session.execute(src_stmt)
                source_map = {row[0]: row[1] for row in src_result.fetchall()}

        results: list[dict] = []
        for doc_id, content_text, file_id, similarity in rows:
            if float(similarity) < threshold:
                continue
            results.append({
                "document_id": str(doc_id),
                "file_id": str(file_id) if file_id else None,
                "source_name": source_map.get(file_id, "") if file_id else "",
                "content_preview": content_text[:100].replace("\n", " ") if content_text else "",
                "similarity": round(float(similarity), 4),
            })
            if len(results) >= topn:
                break

        return results
