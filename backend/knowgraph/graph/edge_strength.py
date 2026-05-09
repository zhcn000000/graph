from collections import defaultdict

from ..database.graph import AgeGraphManager
from .schema import ExtractedTriple


def _entity_type_from_uri(uri: str) -> str:
    if uri.startswith("cidoc:"):
        parts = uri.split("/", 1)
        return parts[0].replace("cidoc:", "")
    return ""


class TripleBasedEdgeQuerier:
    def __init__(self, graph_manager: AgeGraphManager | None = None):
        self.graph_manager = graph_manager or AgeGraphManager()

    async def query_edges_by_entity_names(
        self,
        names: list[str],
        max_per_name: int = 20,
    ) -> dict[str, list[ExtractedTriple]]:
        edges_by_name: dict[str, list[ExtractedTriple]] = defaultdict(list)
        if not names:
            return edges_by_name

        edge_rows = await self.graph_manager.aquery_edge_connections_by_entity_names(names)
        for row in edge_rows:
            query_name = row["query_name"]
            if len(edges_by_name[query_name]) >= max_per_name:
                continue
            triple_data = {
                "subject": {
                    "name": row.get("subject_name", ""),
                    "entity_type": _entity_type_from_uri(str(row.get("start_node_uri", ""))),
                },
                "predicate": {
                    "predicate": str(row.get("relationship_type", "")),
                    "strength": row.get("connection_strength"),
                },
                "object": {
                    "name": row.get("object_name", ""),
                    "entity_type": _entity_type_from_uri(str(row.get("end_node_uri", ""))),
                },
                "description": row.get("description"),
            }
            triple = ExtractedTriple.model_validate(triple_data)
            edges_by_name[query_name].append(triple)
        return edges_by_name
