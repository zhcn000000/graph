import operator
import warnings
from collections import Counter
from typing import NamedTuple
from uuid import UUID

import pandas as pd
from networkx import DiGraph, ego_graph, pagerank
from sqlalchemy import Float, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from knowgraph.documents.embedder import aembed_documents, arerank_documents
from knowgraph.documents.models import Document
from knowgraph.documents.splitter import asplit_content
from knowgraph.documents.tokenizer import atokenize_content
from knowgraph.graph.edge_strength import EdgeConnectionInfo, EdgeStrengthCalculator, TripleBasedEdgeQuerier
from knowgraph.graph.triples import CSVRowInput, LLMExtractor

from .database import DatabaseManager
from .graph import AgeGraphManager
from .source import SourceStore
from .tables import ArtifactRawTable, DocumentTable, Source
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
    def __init__(self, dbname: str = "data") -> None:
        self.__source = SourceStore(dbname)
        self.__db = DatabaseManager(dbname)
        self._graph_manager: AgeGraphManager | None = None
        self._edge_querier: TripleBasedEdgeQuerier | None = None
        self._edge_calculator: EdgeStrengthCalculator | None = None
        self._extractor: LLMExtractor | None = None

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

    @property
    def extractor(self) -> LLMExtractor:
        if self._extractor is None:
            self._extractor = LLMExtractor()
        return self._extractor

    async def _extract_and_update_graph(self, content: str, full_graph: DiGraph) -> set[str]:
        try:
            triples = await self.extractor.aextract_from_document(Document(content=content))
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
            return entity_uris
        except Exception:
            warnings.warn(
                "LLM extraction failed, continuing without extracted entities.",
                UserWarning,
                stacklevel=2,
            )
            return set()

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

            insert_values.append({
                "file_id": file_id,
                "content": doc.content,
                "vector": vectors,
                "bmvector": bmvector,
                "entities": list(entity_uris),
                "meta": doc.metadata,
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
        # @# operator computes maxsim between two vector[] types
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

        # Step 2: Batch traverse from all found vertices, build unified graph for PageRank
        unified_graph = DiGraph()
        traverse_uris = [uri for uri, _ in entity_uris_with_scores[: max(topn * 2, 20)] if uri in vertex_map]
        if traverse_uris:
            unified_graph = await self.graph_manager.atraverse_multi(traverse_uris, max_hops=max_hops)

        if unified_graph.number_of_nodes() == 0:
            return []

        # Step 3: Build URI → node_key lookup for path extraction
        uri_to_node_key: dict[str, object] = {}
        for node_key in unified_graph.nodes():
            node_uri = unified_graph.nodes[node_key].get("uri", "")
            if node_uri:
                uri_to_node_key[node_uri] = node_key

        # Step 5: PageRank with personalization from entity scores
        personalization: dict[str, float] = {}
        for node_key in unified_graph.nodes():
            node_uri = unified_graph.nodes[node_key].get("uri", "")
            personalization[node_key] = entity_score_map.get(node_uri, 0.0)

        total_pers = sum(personalization.values())
        if total_pers > 0:
            pr_scores = pagerank(unified_graph, personalization=personalization)
        else:
            pr_scores = pagerank(unified_graph)

        # Step 6: Query edges by entity names via edge_querier
        names: list[str] = [
            str(vertex_map[uri]["name"])
            for uri in entity_score_map
            if uri in vertex_map and vertex_map[uri].get("name")
        ][:30]

        edges_by_name = await self.edge_querier.query_edges_by_entity_names(names)

        # Step 7: Re-rank edges against current query
        combined_query = " ".join(queries)
        all_edges: list[EdgeConnectionInfo] = []
        for edges in edges_by_name.values():
            all_edges.extend(edges)
        if all_edges:
            await self.edge_calculator.compute_strength_for_edges(combined_query, all_edges)

        # Step 8: Combine PageRank scores with edge strength, populate path
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

            # Extract ego subgraph for this entity's local neighborhood
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
                    col(Source.name),
                    col(Source.link),
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
                    name=row[3],
                    link=row[4],
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
                        name=meta.get("file_name"),
                        link=meta.get("file_hash"),
                        metadata=meta,
                    ),
                )
            return documents

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

    async def aload_from_csv(self, csv_path: str) -> list[UUID]:
        structured_graph = DiGraph()
        documents: list[Document] = []
        source_infos: list[dict] = []
        extraction_contents: list[str | None] = []
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                row_input = CSVRowInput(**{k: v for k, v in row_dict.items() if pd.notna(v)})
            except Exception as e:
                warnings.warn(f"Skipping invalid CSV row: {e}", UserWarning, stacklevel=2)
                continue

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
            documents.append(doc)
            extraction_contents.append(row_input.description or None)
            source_infos.append({
                "name": row_input.title,
                "link": row_input.detail_url,
            })

        if not documents:
            return []

        if structured_graph.number_of_nodes() > 0:
            await self.graph_manager.afrom_networkx(structured_graph)

        async with self.__db.asession() as session:
            for info in source_infos:
                stmt = (
                    insert(Source)
                    .values(name=info["name"], link=info["link"])
                    .on_conflict_do_nothing(index_elements=[col(Source.name)])
                )
                await session.execute(stmt)
            await session.commit()

        await self.aadd_documents(documents, extraction_contents=extraction_contents)

        source_names = list({d.name for d in documents if d.name})
        file_ids: list[UUID] = []
        if source_names:
            file_ids = await self.__source.aget_id_by_names(source_names)

        return file_ids

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
            documents.append(doc)
            extraction_contents.append(row_input.description or None)
            source_infos.append({
                "name": row_input.title,
                "link": row_input.detail_url,
                "artifact_id": artifact.id,
            })

        if not documents:
            return []

        if structured_graph.number_of_nodes() > 0:
            await self.graph_manager.afrom_networkx(structured_graph)

        async with self.__db.asession() as session:
            for info in source_infos:
                stmt = (
                    insert(Source)
                    .values(name=info["name"], link=info["link"], artifact_id=info["artifact_id"])
                    .on_conflict_do_nothing(index_elements=[col(Source.name)])
                )
                await session.execute(stmt)
            await session.commit()

        await self.aadd_documents(documents, extraction_contents=extraction_contents)

        source_names = list({d.name for d in documents if d.name})
        file_ids: list[UUID] = []
        if source_names:
            file_ids = await self.__source.aget_id_by_names(source_names)

        return file_ids

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
