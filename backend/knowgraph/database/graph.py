from __future__ import annotations

from typing import Any

from age import Edge, Path, Vertex
from networkx import DiGraph

from knowgraph.database.database import DatabaseManager
from knowgraph.utils.environments import POSTGRES_DB

GRAPH_LABEL = "artifact_graph"


class AgeGraphManager:
    def __init__(self, graph_name: str = GRAPH_LABEL, dbname: str = POSTGRES_DB):
        self.graph_name = graph_name
        self.__db = DatabaseManager(dbname)

    async def aexecute_cypher(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        read_only: bool = True,
    ) -> list[dict[str, Any]]:
        async with self.__db.aconnection() as conn:
            await conn.set_autocommit(read_only)
            result = await conn.execute(cypher, params or {})  # type: ignore
            if read_only:
                rows = await result.fetchall()
                if rows and result.description:
                    columns = [desc[0] for desc in result.description]
                    return [dict(zip(columns, row, strict=False)) for row in rows]
                return []
            await conn.commit()
            return []

    @staticmethod
    def digraph_to_json(graph: DiGraph) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        for node_uri, data in graph.nodes(data=True):
            node_data: dict[str, Any] = {"uri": node_uri}
            node_data.update(data)
            nodes.append(node_data)

        edges: list[dict[str, Any]] = []
        for u, v, data in graph.edges(data=True):
            edge_data: dict[str, Any] = {"start_uri": u, "end_uri": v}
            edge_data.update(data)
            edges.append(edge_data)

        return {"nodes": nodes, "edges": edges}

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

    async def amupsert_vertex(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        if "uri" not in properties:
            return None

        set_parts: list[str] = []
        params: dict[str, Any] = {"uri": properties["uri"]}
        for k, v in properties.items():
            if k != "uri":
                set_parts.append(f"v.{k} = ${k}")
                params[k] = v

        set_clause = ", ".join(set_parts) if set_parts else "v.uri = $uri"

        cypher = f"""
        MERGE (v:{label} {{uri: $uri}})
        SET {set_clause}
        RETURN id(v) as id, labels(v) as labels, v.uri as uri, v.name as name, v.entity_type as entity_type
        """
        try:
            results = await self.aexecute_cypher(cypher, params, read_only=False)
            if results:
                row = results[0]
                return {
                    "id": row.get("id"),
                    "label": (row.get("labels") or [label])[0] if row.get("labels") else label,
                    "uri": properties.get("uri"),
                    "name": properties.get("name"),
                    "entity_type": properties.get("entity_type"),
                    **{k: v for k, v in properties.items() if k not in {"id", "uri", "name", "entity_type"}},
                }
        except Exception:
            pass
        return None

    async def aget_vertex(
        self,
        uri: str,
        label: str | None = None,
    ) -> dict[str, Any] | None:
        label_clause = f":{label}" if label else ""
        cypher = f"""
        MATCH (v{label_clause} {{uri: $uri}})
        RETURN id(v) as id, labels(v) as labels,
               v.uri as uri, v.name as name,
               v.entity_type as entity_type, v.description as description
        """
        try:
            results = await self.aexecute_cypher(cypher, {"uri": uri})
            if results:
                row = results[0]
                return {
                    "id": row.get("id"),
                    "label": (row.get("labels") or [""])[0],
                    "uri": row.get("uri"),
                    "name": row.get("name"),
                    "entity_type": row.get("entity_type"),
                    "description": row.get("description"),
                }
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
            results = await self.aexecute_cypher(cypher, {"uri": uri}, read_only=False)
            if results and results[0].get("deleted_count", 0) > 0:
                return True
        except Exception:
            pass
        return False

    async def amupsert_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
        start_label: str | None = None,
        end_label: str | None = None,
    ) -> dict[str, Any] | None:
        props: dict[str, Any] = dict(properties or {})
        props["start_uri"] = start_uri
        props["end_uri"] = end_uri
        props["predicate_uri"] = f"cidoc:relationship/{relationship_type}"

        props_set = ", ".join([f"r.{k} = ${k}" for k in props])

        start_match = f":{start_label}" if start_label else ""
        end_match = f":{end_label}" if end_label else ""

        cypher = f"""
        MATCH (s{start_match} {{uri: $start_uri}})
        MATCH (e{end_match} {{uri: $end_uri}})
        MERGE (s)-[r:{relationship_type} {{uri: $predicate_uri}}]->(e)
        SET {props_set}
        RETURN id(r) as id, r.uri as uri, type(r) as relationship_type
        """

        params: dict[str, Any] = {
            "start_uri": start_uri,
            "end_uri": end_uri,
            "predicate_uri": props["predicate_uri"],
        }
        params.update(props)

        try:
            results = await self.aexecute_cypher(cypher, params, read_only=False)
            if results:
                row = results[0]
                return {
                    "id": row.get("id"),
                    "label": relationship_type,
                    "uri": props.get("predicate_uri"),
                    "start_uri": start_uri,
                    "end_uri": end_uri,
                    "relationship_type": row.get("relationship_type"),
                    **{k: v for k, v in props.items() if k not in {"start_uri", "end_uri", "predicate_uri"}},
                }
        except Exception:
            pass
        return None

    async def aget_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str | None = None,
    ) -> dict[str, Any] | None:
        rel_clause = f":{relationship_type}" if relationship_type else ""

        cypher = f"""
        MATCH (s {{uri: $start_uri}})-[r{rel_clause}]->(e {{uri: $end_uri}})
        RETURN id(r) as id, r.uri as uri, type(r) as relationship_type,
               s.uri as start_uri, e.uri as end_uri
        """
        try:
            results = await self.aexecute_cypher(cypher, {"start_uri": start_uri, "end_uri": end_uri})
            if results:
                row = results[0]
                return {
                    "id": row.get("id"),
                    "label": row.get("relationship_type"),
                    "uri": row.get("uri"),
                    "start_uri": row.get("start_uri"),
                    "end_uri": row.get("end_uri"),
                    "relationship_type": row.get("relationship_type"),
                }
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
            results = await self.aexecute_cypher(
                cypher,
                {"start_uri": start_uri, "end_uri": end_uri},
                read_only=False,
            )
            if results and results[0].get("deleted_count", 0) > 0:
                return True
        except Exception:
            pass
        return False

    async def atraverse(
        self,
        start_uri: str,
        max_hops: int = 3,
        direction: str = "both",
    ) -> DiGraph:
        if direction == "outbound":
            rel_pattern = f"-[*1..{max_hops}]->"
        elif direction == "inbound":
            rel_pattern = f"<-[*1..{max_hops}]-"
        else:
            rel_pattern = f"-[*1..{max_hops}]-"

        cypher = f"""
        MATCH path = (start {{uri: $uri}}){rel_pattern}(end)
        RETURN nodes(path) as nodes, relationships(path) as edges
        """
        try:
            results = await self.aexecute_cypher(cypher, {"uri": start_uri})
            return self._path_rows_to_digraph(results)
        except Exception:
            return DiGraph()

    async def afind_paths(
        self,
        start_uri: str,
        end_uri: str,
        max_hops: int = 5,
    ) -> DiGraph:
        cypher = f"""
        MATCH path = shortestPath((start {{uri: $start_uri}})-[*]->(end {{uri: $end_uri}}))
        WHERE size(relationships(path)) <= {max_hops}
        RETURN nodes(path) as nodes, relationships(path) as edges
        """
        try:
            results = await self.aexecute_cypher(
                cypher,
                {"start_uri": start_uri, "end_uri": end_uri},
            )
            return self._path_rows_to_digraph(results)
        except Exception:
            return DiGraph()

    @staticmethod
    def _path_rows_to_digraph(rows: list[dict[str, Any]]) -> DiGraph:
        graph = DiGraph()
        seen_nodes: set[str] = set()
        seen_edges: set[tuple] = set()
        for row in rows:
            for node_item in row.get("nodes", []):
                if not node_item:
                    continue
                uri = node_item.get("uri")
                if uri is None or uri in seen_nodes:
                    continue
                seen_nodes.add(uri)
                labels = node_item.get("labels") or []
                graph.add_node(
                    uri,
                    label=labels[0] if labels else None,
                    name=node_item.get("name"),
                    entity_type=node_item.get("entity_type"),
                    id=node_item.get("id"),
                )
            for rel_item in row.get("edges", []):
                if not rel_item:
                    continue
                su = rel_item.get("start_uri")
                eu = rel_item.get("end_uri")
                eid = rel_item.get("id")
                key = (su, eu, eid)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                graph.add_edge(
                    su,
                    eu,
                    id=eid,
                    label=rel_item.get("type") or rel_item.get("label"),
                    uri=rel_item.get("uri"),
                    relationship_type=rel_item.get("type") or rel_item.get("label"),
                )
        return graph

    async def afrom_networkx(self, graph: DiGraph) -> bool:
        try:
            nodes_by_label: dict[str, list[dict[str, Any]]] = {}
            for node_uri, data in graph.nodes(data=True):
                label = data.get("label", "Entity")
                props: dict[str, Any] = {"uri": data.get("uri", node_uri)}

                if data.get("name") is not None:
                    props["name"] = data["name"]
                elif "name" not in props:
                    props["name"] = str(node_uri)

                if data.get("entity_type") is not None:
                    props["entity_type"] = data["entity_type"]

                extra = data.get("properties", {})
                if isinstance(extra, dict):
                    for k, v in extra.items():
                        if k not in props:
                            props[k] = v

                nodes_by_label.setdefault(label, []).append(props)

            for label, nodes in nodes_by_label.items():
                cypher = f"""
                UNWIND $nodes AS node
                MERGE (v:{label} {{uri: node.uri}})
                SET v += node
                """
                await self.aexecute_cypher(cypher, {"nodes": nodes}, read_only=False)

            edges_by_type: dict[str, list[dict[str, Any]]] = {}
            for u, v, data in graph.edges(data=True):
                rel_type = data.get("label", "related_to")
                start_uri = graph.nodes[u].get("uri", u)
                end_uri = graph.nodes[v].get("uri", v)
                predicate_uri = data.get("uri", f"cidoc:relationship/{rel_type}")

                props: dict[str, Any] = {
                    "uri": predicate_uri,
                    "predicate_uri": predicate_uri,
                }
                extra = data.get("properties", {})
                if isinstance(extra, dict):
                    for k, val in extra.items():
                        if k not in props:
                            props[k] = val

                edges_by_type.setdefault(rel_type, []).append({
                    "s": start_uri,
                    "e": end_uri,
                    "p": props,
                })

            for rel_type, edges in edges_by_type.items():
                cypher = f"""
                UNWIND $edges AS edge
                MATCH (s {{uri: edge.s}})
                MATCH (e {{uri: edge.e}})
                MERGE (s)-[r:{rel_type} {{uri: edge.p.uri}}]->(e)
                SET r += edge.p
                """
                await self.aexecute_cypher(cypher, {"edges": edges}, read_only=False)

            return True
        except Exception:
            raise

    async def ato_networkx(self, query: str | None = None) -> DiGraph:

        graph = DiGraph()

        def add_node_to_networkx(node):
            graph.add_node(node.id, label=node.label, properties=node.properties)

        def add_edge_to_networkx(edge):
            graph.add_edge(edge.start_id, edge.end_id, label=edge.label, properties=edge.properties)

        def add_path(path):
            for x in path:
                if isinstance(x, Path):
                    add_path(x)
            for x in path:
                if isinstance(x, Vertex):
                    add_node_to_networkx(x)
            for x in path:
                if isinstance(x, Edge):
                    add_edge_to_networkx(x)

        async with self.__db.aconnection() as conn:
            result = await conn.execute(query)  # type: ignore
            rows = await result.fetchall()
            for row in rows:
                for x in row:
                    if isinstance(x, Path):
                        add_path(x)
                    elif isinstance(x, Edge):
                        add_edge_to_networkx(x)
                    elif isinstance(x, Vertex):
                        add_node_to_networkx(x)
        return graph
