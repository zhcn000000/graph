from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..database.graph import AgeGraphManager
from ..documents.embedder import arerank_documents
from ..documents.models import Document


@dataclass
class EdgeConnectionInfo:
    start_node_uri: str
    end_node_uri: str
    relationship_type: str
    subject_name: str
    object_name: str
    description: str | None
    predicate_description: str
    connection_strength: float | None = None


class EdgeStrengthCalculator:
    def __init__(
        self,
        graph_manager: AgeGraphManager | None = None,
        batch_size: int = 32,
    ):
        self.graph_manager = graph_manager or AgeGraphManager()
        self.batch_size = batch_size

    @staticmethod
    def _parse_edge_rows(results: list[dict[str, Any]]) -> list[EdgeConnectionInfo]:
        edges = []
        for row in results:
            predicate_desc = row.get("relationship_type", "").replace("_", " ")
            edge_info = EdgeConnectionInfo(
                start_node_uri=row.get("start_node_uri", ""),
                end_node_uri=row.get("end_node_uri", ""),
                relationship_type=row.get("relationship_type", ""),
                subject_name=row.get("subject_name", ""),
                object_name=row.get("object_name", ""),
                description=row.get("description"),
                predicate_description=predicate_desc,
                connection_strength=row.get("connection_strength"),
            )
            edges.append(edge_info)
        return edges

    def _construct_edge_query(self, edge_info: EdgeConnectionInfo) -> str:
        parts = [
            f"Subject: {edge_info.subject_name}",
            f"Relationship: {edge_info.predicate_description}",
            f"Object: {edge_info.object_name}",
        ]
        if edge_info.description:
            parts.append(f"Description: {edge_info.description}")
        return " | ".join(parts)

    def _construct_edge_document(self, edge_info: EdgeConnectionInfo) -> str:
        parts = [
            f"{edge_info.subject_name}",
            f"is {edge_info.predicate_description}",
            f"{edge_info.object_name}",
        ]
        if edge_info.description:
            parts.append(f"({edge_info.description})")
        return " ".join(parts)

    async def _get_all_edges(self) -> list[EdgeConnectionInfo]:
        cypher = """
        MATCH (s)-[r]->(o)
        RETURN r.uri as predicate_uri,
               type(r) as relationship_type,
               startNode(r).uri as start_node_uri,
               startNode(r).name as subject_name,
               endNode(r).uri as end_node_uri,
               endNode(r).name as object_name,
               r.description as description,
               r.connection_strength as connection_strength
        LIMIT 10000
        """
        results = await self.graph_manager.aexecute_cypher(cypher, {})
        return self._parse_edge_rows(results)

    async def compute_strength_for_edges(
        self,
        query: str,
        edges: list[EdgeConnectionInfo] | None = None,
    ) -> list[EdgeConnectionInfo]:
        if edges is None:
            edges = await self._get_all_edges()

        if not edges:
            return []

        edge_docs = [self._construct_edge_document(e) for e in edges]
        documents = [Document(content=doc) for doc in edge_docs]

        reranked = await arerank_documents(query, documents, topn=None, skip_sorting=True)

        for edge, reranked_doc in zip(edges, reranked, strict=False):
            edge.connection_strength = reranked_doc.query_score

        return edges

    async def compute_and_store_strength(
        self,
        query: str,
        edges: list[EdgeConnectionInfo] | None = None,
    ) -> list[EdgeConnectionInfo]:
        edges_with_strength = await self.compute_strength_for_edges(query, edges)

        for edge in edges_with_strength:
            if edge.connection_strength is not None:
                await self.graph_manager.amupsert_edge(
                    start_uri=edge.start_node_uri,
                    end_uri=edge.end_node_uri,
                    relationship_type=edge.relationship_type,
                    properties={"connection_strength": edge.connection_strength},
                )

        return edges_with_strength

    async def batch_compute_and_store(
        self,
        queries: list[str],
        edges: list[EdgeConnectionInfo] | None = None,
    ) -> list[list[EdgeConnectionInfo]]:
        if edges is None:
            edges = await self._get_all_edges()

        all_results = []
        for i in range(0, len(queries), self.batch_size):
            batch_queries = queries[i : i + self.batch_size]
            combined_query = " ".join([f"[{q}]" for q in batch_queries])

            batch_results = await self.compute_and_store_strength(combined_query, edges)
            all_results.append(batch_results)

        return all_results

    async def compute_triple_strength(
        self,
        subject_name: str,
        predicate: str,
        object_name: str,
        description: str | None = None,
        query: str | None = None,
    ) -> float | None:
        predicate_desc = predicate.replace("_", " ")

        edge_info = EdgeConnectionInfo(
            start_node_uri="",
            end_node_uri="",
            relationship_type=predicate,
            subject_name=subject_name,
            object_name=object_name,
            description=description,
            predicate_description=predicate_desc,
        )

        if query is None:
            query = f"{subject_name} {predicate_desc} {object_name}"

        doc = Document(content=self._construct_edge_document(edge_info))
        reranked = await arerank_documents(query, [doc], topn=1)

        if reranked:
            return reranked[0].query_score
        return None

    async def update_edge_strength_property(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str,
        connection_strength: float,
    ) -> bool:
        result = await self.graph_manager.amupsert_edge(
            start_uri=start_uri,
            end_uri=end_uri,
            relationship_type=relationship_type,
            properties={"connection_strength": connection_strength},
        )
        return result is not None


class TripleBasedEdgeQuerier:
    def __init__(self, graph_manager: AgeGraphManager | None = None):
        self.graph_manager = graph_manager or AgeGraphManager()
        self.strength_calculator = EdgeStrengthCalculator(graph_manager)

    def construct_query_from_triple(
        self,
        subject_name: str,
        predicate: str,
        object_name: str,
        description: str | None = None,
    ) -> str:
        predicate_clean = predicate.replace("_", " ")
        query_parts = [
            f"{subject_name}",
            f"{predicate_clean}",
            f"{object_name}",
        ]
        if description:
            query_parts.append(f"({description})")
        return " ".join(query_parts)

    async def query_edges_by_triple(
        self,
        subject_name: str | None = None,
        predicate: str | None = None,
        object_name: str | None = None,
        description: str | None = None,
        min_strength: float | None = None,
        limit: int = 100,
    ) -> list[EdgeConnectionInfo]:
        conditions = []
        params: dict[str, Any] = {}

        if subject_name:
            conditions.append("startNode(r).name CONTAINS $subject_name")
            params["subject_name"] = subject_name
        if predicate:
            conditions.append("type(r) = $predicate")
            params["predicate"] = predicate
        if object_name:
            conditions.append("endNode(r).name CONTAINS $object_name")
            params["object_name"] = object_name
        if description:
            conditions.append("r.description CONTAINS $description")
            params["description"] = description

        where_clause = " AND ".join(conditions) if conditions else "true"

        cypher = f"""
        MATCH (s)-[r]->(o)
        WHERE {where_clause}
        RETURN r.uri as predicate_uri,
               type(r) as relationship_type,
               startNode(r).uri as start_node_uri,
               startNode(r).name as subject_name,
               endNode(r).uri as end_node_uri,
               endNode(r).name as object_name,
               r.description as description,
               r.connection_strength as connection_strength
        LIMIT {limit}
        """

        results = await self.graph_manager.aexecute_cypher(cypher, params)

        edges = []
        for row in results:
            if min_strength is not None:
                strength = row.get("connection_strength")
                if strength is None or strength < min_strength:
                    continue

            predicate_desc = row.get("relationship_type", "").replace("_", " ")
            edge_info = EdgeConnectionInfo(
                start_node_uri=row.get("start_node_uri", ""),
                end_node_uri=row.get("end_node_uri", ""),
                relationship_type=row.get("relationship_type", ""),
                subject_name=row.get("subject_name", ""),
                object_name=row.get("object_name", ""),
                description=row.get("description"),
                predicate_description=predicate_desc,
                connection_strength=row.get("connection_strength"),
            )
            edges.append(edge_info)

        return edges

    async def rerank_edges_by_query(
        self,
        query: str,
        edges: list[EdgeConnectionInfo] | None = None,
        topn: int | None = None,
    ) -> list[EdgeConnectionInfo]:
        if edges is None:
            edges = await self._get_all_edges()

        if not edges:
            return []

        edge_docs = [self._construct_edge_document(e) for e in edges]
        documents = [Document(content=doc) for doc in edge_docs]

        reranked = await arerank_documents(query, documents, topn=topn, skip_sorting=True)

        reranked_edges = []
        for edge, reranked_doc in zip(edges, reranked, strict=False):
            edge.connection_strength = reranked_doc.query_score
            reranked_edges.append(edge)

        return reranked_edges

    def _construct_edge_document(self, edge_info: EdgeConnectionInfo) -> str:
        parts = [
            f"{edge_info.subject_name}",
            f"is {edge_info.predicate_description}",
            f"{edge_info.object_name}",
        ]
        if edge_info.description:
            parts.append(f"({edge_info.description})")
        return " ".join(parts)

    async def _get_all_edges(self) -> list[EdgeConnectionInfo]:
        return await self.strength_calculator._get_all_edges()
