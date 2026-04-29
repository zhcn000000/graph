from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knowgraph.database.database import DatabaseManager
from knowgraph.utils.environments import POSTGRES_DB

GRAPH_LABEL = "artifact_graph"


@dataclass
class Vertex:
    id: int | None = None
    uri: str | None = None
    name: str | None = None
    entity_type: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    id: int | None = None
    uri: str | None = None
    start_node_uri: str | None = None
    end_node_uri: str | None = None
    predicate_uri: str | None = None
    relationship_type: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPath:
    nodes: list[Vertex] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


class AgeGraphManager:
    def __init__(self, graph_name: str = GRAPH_LABEL, dbname: str = POSTGRES_DB):
        self.graph_name = graph_name
        self.__db = DatabaseManager(dbname)

    async def _execute_cypher(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        read_only: bool = True,
    ) -> list[dict[str, Any]]:
        async with self.__db.aconnection() as conn:
            await conn.set_autocommit(not read_only)
            result = await conn.execute(cypher, params or {})  # type: ignore
            if read_only:
                rows = await result.fetchall()
                if rows and result.description:
                    columns = [desc[0] for desc in result.description]
                    return [dict(zip(columns, row, strict=False)) for row in rows]
                return []
            return []

    async def acreate_graph(self) -> bool:
        try:
            async with self.__db.aconnection() as conn:
                await conn.set_autocommit(False)
                result = await conn.execute(f"SELECT * FROM ag_graph WHERE graph_name = '{self.graph_name}';")  # type: ignore
                exists = await result.fetchone()

                if not exists:
                    await conn.execute(f"SELECT create_graph('{self.graph_name}');")  # type: ignore
                    await conn.commit()
                    return True
                await conn.commit()
                return False
        except Exception:
            return False

    async def adrop_graph(self) -> bool:
        try:
            async with self.__db.aconnection() as conn:
                await conn.set_autocommit(False)
                result = await conn.execute(f"SELECT * FROM ag_graph WHERE graph_name = '{self.graph_name}';")  # type: ignore
                exists = await result.fetchone()

                if exists:
                    await conn.execute(f"SELECT drop_graph('{self.graph_name}', true);")  # type: ignore
                    await conn.commit()
                    return True
                await conn.commit()
                return False
        except Exception:
            return False

    async def acreate_vertex(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> Vertex | None:
        props_map = ", ".join([f"{k} = ${k}" for k in properties])

        cypher = f"""
        MERGE (v:{label} {{{props_map}}})
        RETURN id(v) as id, v.uri as uri, v.name as name, v.entity_type as entity_type
        """

        try:
            results = await self._execute_cypher(cypher, properties, read_only=False)
            if results:
                row = results[0]
                return Vertex(
                    id=row.get("id"),
                    uri=properties.get("uri"),
                    name=properties.get("name"),
                    entity_type=properties.get("entity_type"),
                    properties=properties,
                )
        except Exception:
            pass
        return None

    async def aget_vertex(
        self,
        uri: str,
        label: str | None = None,
    ) -> Vertex | None:
        label_clause = f":{label}" if label else ""
        cypher = f"""
        MATCH (v{label_clause} {{uri: $uri}})
        RETURN id(v) as id, v.uri as uri, v.name as name, v.entity_type as entity_type
        """

        try:
            results = await self._execute_cypher(cypher, {"uri": uri})
            if results:
                row = results[0]
                props = {k: v for k, v in row.items() if k not in {"id", "uri", "name", "entity_type"}}
                return Vertex(
                    id=row.get("id"),
                    uri=row.get("uri"),
                    name=row.get("name"),
                    entity_type=row.get("entity_type"),
                    properties=props,
                )
        except Exception:
            pass
        return None

    async def aupdate_vertex(
        self,
        uri: str,
        properties: dict[str, Any],
        label: str | None = None,
    ) -> Vertex | None:
        label_clause = f":{label}" if label else ""
        props_set = ", ".join([f"v.{k} = ${k}" for k in properties])

        cypher = f"""
        MATCH (v{label_clause} {{uri: $uri}})
        SET {props_set}
        RETURN id(v) as id, v.uri as uri, v.name as name, v.entity_type as entity_type
        """

        params = {"uri": uri}
        params.update(properties)

        try:
            results = await self._execute_cypher(cypher, params, read_only=False)
            if results:
                row = results[0]
                return Vertex(
                    id=row.get("id"),
                    uri=row.get("uri"),
                    name=row.get("name"),
                    entity_type=row.get("entity_type"),
                    properties=properties,
                )
        except Exception:
            pass
        return None

    async def adelete_vertex(self, uri: str, label: str | None = None) -> bool:
        label_clause = f":{label}" if label else ""
        cypher = f"""
        MATCH (v{label_clause} {{uri: $uri}})
        DETACH DELETE v
        RETURN count(*) as deleted_count
        """

        try:
            results = await self._execute_cypher(cypher, {"uri": uri}, read_only=False)
            if results and results[0].get("deleted_count", 0) > 0:
                return True
        except Exception:
            pass
        return False

    async def acreate_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge | None:
        props = properties or {}
        props["start_uri"] = start_uri
        props["end_uri"] = end_uri
        props["predicate_uri"] = f"cidoc:relationship/{relationship_type}"

        props_map = ", ".join([f"r.{k} = ${k}" for k in props.keys()])

        cypher = f"""
        MATCH (s {{uri: $start_uri}})
        MATCH (e {{uri: $end_uri}})
        MERGE (s)-[r:{relationship_type} {{uri: $predicate_uri}}]->(e)
        SET r += ${{props_map}}
        RETURN id(r) as id, r.uri as uri, type(r) as relationship_type
        """

        params = {"start_uri": start_uri, "end_uri": end_uri, "predicate_uri": props["predicate_uri"]}
        params.update(props)

        try:
            results = await self._execute_cypher(cypher, params, read_only=False)
            if results:
                row = results[0]
                return Edge(
                    id=row.get("id"),
                    uri=props.get("predicate_uri"),
                    start_node_uri=start_uri,
                    end_node_uri=end_uri,
                    predicate_uri=props.get("predicate_uri"),
                    relationship_type=row.get("relationship_type"),
                    properties=props,
                )
        except Exception:
            pass
        return None

    async def aget_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str | None = None,
    ) -> Edge | None:
        rel_clause = f":{relationship_type}" if relationship_type else ""

        cypher = f"""
        MATCH (s {{uri: $start_uri}})-[r{rel_clause}]->(e {{uri: $end_uri}})
        RETURN id(r) as id, r.uri as uri, type(r) as relationship_type,
               startNode(r).uri as start_node_uri, endNode(r).uri as end_node_uri
        """

        try:
            results = await self._execute_cypher(cypher, {"start_uri": start_uri, "end_uri": end_uri})
            if results:
                row = results[0]
                props = {
                    k: v
                    for k, v in row.items()
                    if k not in {"id", "uri", "relationship_type", "start_node_uri", "end_node_uri"}
                }
                return Edge(
                    id=row.get("id"),
                    uri=row.get("uri"),
                    start_node_uri=row.get("start_node_uri"),
                    end_node_uri=row.get("end_node_uri"),
                    predicate_uri=row.get("uri"),
                    relationship_type=row.get("relationship_type"),
                    properties=props,
                )
        except Exception:
            pass
        return None

    async def adelete_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str,
    ) -> bool:
        cypher = f"""
        MATCH (s {{uri: $start_uri}})-[r:{relationship_type}]->(e {{uri: $end_uri}})
        DELETE r
        RETURN count(*) as deleted_count
        """

        try:
            results = await self._execute_cypher(cypher, {"start_uri": start_uri, "end_uri": end_uri}, read_only=False)
            if results and results[0].get("deleted_count", 0) > 0:
                return True
        except Exception:
            pass
        return False

    async def aget_neighbors(
        self,
        uri: str,
        direction: str = "both",
        max_hops: int = 1,
    ) -> list[Vertex]:
        if direction == "outbound":
            rel_pattern = "-[r]->"
        elif direction == "inbound":
            rel_pattern = "<-[r]-"
        else:
            rel_pattern = "-[r]-"

        cypher = f"""
        MATCH (v {{uri: $uri}}){rel_pattern}*(1..{max_hops})(neighbor)
        WHERE v.uri = $uri
        WITH DISTINCT neighbor as n
        RETURN id(n) as id, n.uri as uri, n.name as name, n.entity_type as entity_type
        """

        try:
            results = await self._execute_cypher(cypher, {"uri": uri, "max_hops": max_hops})
            vertices = []
            for row in results:
                props = {k: v for k, v in row.items() if k not in {"id", "uri", "name", "entity_type"}}
                vertices.append(
                    Vertex(
                        id=row.get("id"),
                        uri=row.get("uri"),
                        name=row.get("name"),
                        entity_type=row.get("entity_type"),
                        properties=props,
                    ),
                )
            return vertices
        except Exception:
            return []

    async def aexecute_cypher(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._execute_cypher(cypher, params, read_only=False)

    async def aquery_by_type(
        self,
        entity_type: str,
        limit: int = 100,
    ) -> list[Vertex]:
        cypher = f"""
        MATCH (v:{entity_type.capitalize()})
        RETURN id(v) as id, v.uri as uri, v.name as name, v.entity_type as entity_type
        LIMIT {limit}
        """

        try:
            results = await self._execute_cypher(cypher)
            vertices = []
            for row in results:
                props = {k: v for k, v in row.items() if k not in {"id", "uri", "name", "entity_type"}}
                vertices.append(
                    Vertex(
                        id=row.get("id"),
                        uri=row.get("uri"),
                        name=row.get("name"),
                        entity_type=row.get("entity_type"),
                        properties=props,
                    ),
                )
            return vertices
        except Exception:
            return []

    async def atraverse(
        self,
        start_uri: str,
        max_hops: int = 3,
        direction: str = "both",
    ) -> GraphPath:
        if direction == "outbound":
            rel_pattern = "-[r]->"
        elif direction == "inbound":
            rel_pattern = "<-[r]-"
        else:
            rel_pattern = "-[r]-"

        cypher = f"""
        MATCH path = (start {{uri: $uri}}){rel_pattern}*(1..{max_hops})(end)
        WITH path
        UNWIND range(0, size(nodes(path)) - 1) as idx
        WITH nodes(path)[idx] as node, idx
        WITH collect(DISTINCT node) as unique_nodes
        UNWIND unique_nodes as n
        RETURN id(n) as id, n.uri as uri, n.name as name, n.entity_type as entity_type
        """

        try:
            results = await self._execute_cypher(cypher, {"uri": start_uri, "max_hops": max_hops})
            nodes = []
            for row in results:
                props = {k: v for k, v in row.items() if k not in {"id", "uri", "name", "entity_type"}}
                nodes.append(
                    Vertex(
                        id=row.get("id"),
                        uri=row.get("uri"),
                        name=row.get("name"),
                        entity_type=row.get("entity_type"),
                        properties=props,
                    ),
                )
            return GraphPath(nodes=nodes, edges=[])
        except Exception:
            return GraphPath(nodes=[], edges=[])

    async def afind_paths(
        self,
        start_uri: str,
        end_uri: str,
        max_hops: int = 5,
    ) -> list[GraphPath]:
        cypher = """
        MATCH path = shortestPath((start {uri: $start_uri})-[*]->(end {uri: $end_uri}))
        WITH path
        UNWIND range(0, size(nodes(path)) - 1) as idx
        WITH nodes(path)[idx] as node, rels(path)[idx] as rel, idx
        ORDER BY idx
        RETURN collect(DISTINCT node) as nodes, collect(DISTINCT rel) as edges
        """

        try:
            results = await self._execute_cypher(
                cypher,
                {"start_uri": start_uri, "end_uri": end_uri, "max_hops": max_hops},
            )
            paths = []
            for row in results:
                nodes = []
                for node in row.get("nodes", []):
                    if node:
                        props = {k: v for k, v in node.items() if k not in {"id", "uri", "name", "entity_type"}}
                        nodes.append(
                            Vertex(
                                id=node.get("id"),
                                uri=node.get("uri"),
                                name=node.get("name"),
                                entity_type=node.get("entity_type"),
                                properties=props,
                            ),
                        )

                edges = []
                for rel in row.get("edges", []):
                    if rel:
                        props = {k: v for k, v in rel.items() if k not in {"id", "uri", "type"}}
                        edges.append(
                            Edge(
                                id=rel.get("id"),
                                uri=rel.get("uri"),
                                relationship_type=rel.get("type"),
                                properties=props,
                            ),
                        )

                paths.append(GraphPath(nodes=nodes, edges=edges))
            return paths
        except Exception:
            return []
