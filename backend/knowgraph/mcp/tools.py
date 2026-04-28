from typing import Any

from fastmcp import FastMCP

from knowgraph.database import RAGMode
from knowgraph.database.ragmode import GraphRAGConfig

mcp = FastMCP("knowgraph")


@mcp.tool()
async def search_rag(
    rag_id: str,
    queries: list[str],
    use_graph: bool = False,
) -> list[dict[str, Any]]:
    rag_mode = RAGMode()
    try:
        from uuid import UUID

        rag_uuid = UUID(rag_id)
        results = await rag_mode.aquery_documents(
            rag_id=rag_uuid,
            queries=queries,
            use_graph=use_graph,
        )
        return [
            {
                "content": r.content,
                "source_name": r.source_name,
                "score": r.score,
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def query_graph(
    queries: list[str],
    max_hops: int = 3,
) -> dict[str, Any]:
    rag_mode = RAGMode()
    try:
        context = await rag_mode.aquery_graph_context(
            queries=queries,
            max_hops=max_hops,
        )
        return context
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_triples(
    entity_uri: str | None = None,
    subject_uri: str | None = None,
    object_uri: str | None = None,
    relationship_type: str | None = None,
) -> list[dict[str, Any]]:
    rag_mode = RAGMode()
    try:
        if entity_uri:
            neighbors = await rag_mode.aget_neighbors(entity_uri, direction="both", max_hops=1)
            triples = []
            for neighbor in neighbors:
                edge = await rag_mode.aget_edge(
                    start_uri=entity_uri,
                    end_uri=neighbor.uri,
                    relationship_type=relationship_type,
                )
                if edge:
                    triples.append({
                        "subject_uri": edge.start_node_uri,
                        "predicate_uri": edge.predicate_uri,
                        "object_uri": edge.end_node_uri,
                        "relationship_type": edge.relationship_type,
                    })
            return triples
        elif subject_uri and object_uri:
            edge = await rag_mode.aget_edge(subject_uri, object_uri, relationship_type)
            if edge:
                return [
                    {
                        "subject_uri": edge.start_node_uri,
                        "predicate_uri": edge.predicate_uri,
                        "object_uri": edge.end_node_uri,
                        "relationship_type": edge.relationship_type,
                    }
                ]
        return []
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def get_entity(
    uri: str,
    label: str | None = None,
) -> dict[str, Any]:
    rag_mode = RAGMode()
    try:
        vertex = await rag_mode.aget_vertex(uri, label)
        if vertex:
            return {
                "uri": vertex.uri,
                "name": vertex.name,
                "entity_type": vertex.entity_type,
                "properties": vertex.properties,
            }
        return {"error": "Entity not found"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def expand_context(
    entity_uri: str,
    max_hops: int = 2,
    direction: str = "both",
) -> dict[str, Any]:
    rag_mode = RAGMode()
    try:
        context = await rag_mode.aexpand_context_by_graph(
            entity_uri=entity_uri,
            max_hops=max_hops,
            direction=direction,
        )
        return context
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_entity_paths(
    start_uri: str,
    end_uri: str,
    max_hops: int = 5,
) -> list[dict[str, Any]]:
    rag_mode = RAGMode()
    try:
        paths = await rag_mode.aget_entity_paths(start_uri, end_uri, max_hops)
        return paths
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def graph_search(
    queries: list[str],
    k: int = 4,
    max_hops: int = 3,
) -> dict[str, Any]:
    rag_mode = RAGMode()
    try:
        config = GraphRAGConfig()
        config.MAX_HOPS = max_hops
        docs, graph_entities = await rag_mode.ahyprid_search_with_graph(
            queries=queries,
            k=k,
            graph_config=config,
        )
        return {
            "documents": [
                {
                    "content": d.content,
                    "source_name": d.source_name,
                    "score": d.query_score if d.query_score is not None else 0.0,
                }
                for d in docs
            ],
            "graph_entities": [
                {
                    "uri": g.entity_uri,
                    "name": g.entity_name,
                    "type": g.entity_type,
                    "score": g.score,
                }
                for g in graph_entities
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def create_graph_entity(
    label: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    rag_mode = RAGMode()
    try:
        vertex = await rag_mode.acreate_vertex(label, properties)
        if vertex:
            return {
                "uri": vertex.uri,
                "name": vertex.name,
                "entity_type": vertex.entity_type,
                "properties": vertex.properties,
            }
        return {"error": "Failed to create vertex"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def create_graph_relation(
    start_uri: str,
    end_uri: str,
    relationship_type: str,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rag_mode = RAGMode()
    try:
        edge = await rag_mode.acreate_edge(start_uri, end_uri, relationship_type, properties)
        if edge:
            return {
                "id": edge.id,
                "uri": edge.uri,
                "start_node_uri": edge.start_node_uri,
                "end_node_uri": edge.end_node_uri,
                "relationship_type": edge.relationship_type,
            }
        return {"error": "Failed to create edge"}
    except Exception as e:
        return {"error": str(e)}
