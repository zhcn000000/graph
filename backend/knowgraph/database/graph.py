from __future__ import annotations

import math
from typing import Any

from age.models import Edge, Path, Vertex
from networkx import DiGraph
from psycopg import sql as pgsql

from knowgraph.database.database import DatabaseManager
from knowgraph.utils.environments import POSTGRES_DB

GRAPH_LABEL = "artifact_graph"


def _quote_cypher_value(value: Any) -> str:
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        elif math.isinf(value):
            return str(value)
        return str(value)
    elif isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    elif isinstance(value, (list, tuple)):
        items = ", ".join(_quote_cypher_value(v) for v in value)
        return f"[{items}]"
    elif isinstance(value, dict):
        pairs = ", ".join(
            f"{_quote_cypher_key(k)}: {_quote_cypher_value(v)}"
            for k, v in value.items()  # type: ignore[arg-type]
        )
        return f"{{{pairs}}}"
    return _quote_cypher_value(str(value))


def _quote_cypher_key(key: object) -> str:
    if isinstance(key, str) and key.replace("_", "").isalnum():
        return key
    return _quote_cypher_value(key)


def _embed_params(cypher: str, params: dict[str, Any]) -> str:
    if not params:
        return cypher
    param_keys: list[str] = list(params.keys())
    param_keys.sort(key=len, reverse=True)
    for key in param_keys:
        placeholder = f"${key}"
        replacement = _quote_cypher_value(params[key])
        cypher = cypher.replace(placeholder, replacement)
    return cypher


def _build_cypher_stmt(graph_name: str, cypher: str, columns: list[str]) -> pgsql.Composable:
    if columns:
        col_parts: list[pgsql.Composable] = []
        for c in columns:
            c = c.strip()
            if not c:
                continue
            if " " in c:
                name, type_name = c.split(" ", 1)
                col_parts.append(pgsql.SQL("{} {}").format(pgsql.Identifier(name), pgsql.Identifier(type_name)))
            else:
                col_parts.append(pgsql.SQL("{} agtype").format(pgsql.Identifier(c)))
        cols: pgsql.Composable = pgsql.SQL(", ").join(col_parts)
    else:
        cols = pgsql.SQL('"v" agtype')

    return pgsql.SQL("SELECT * FROM cypher({graphName}, {cypher}) AS ({columns})").format(  # type: ignore[arg-type]
        graphName=pgsql.Literal(graph_name),
        cypher=pgsql.Literal(cypher),
        columns=cols,
    )


class AgeGraphManager:
    def __init__(self, graph_name: str = GRAPH_LABEL, dbname: str = POSTGRES_DB):
        self.graph_name = graph_name
        self.__db = DatabaseManager(dbname)

    async def aexecute_cypher(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        read_only: bool = True,
    ) -> list[dict[str, Any]]:
        if columns is None:
            columns = []

        cypher_clean = cypher.replace("\n", " ").replace("\t", " ")
        cypher_clean = _embed_params(cypher_clean, params or {})

        stmt = _build_cypher_stmt(self.graph_name, cypher_clean, columns)

        async with self.__db.acursor(read_only=read_only, autocommit=read_only) as cur:
            result = await cur.execute(stmt)  # type: ignore
            rows = await result.fetchall()
            if not result.description:
                return []
            col_names = [desc[0] for desc in result.description]
            return [dict(zip(col_names, row, strict=False)) for row in rows]

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
        async with self.__db.acursor() as cur:
            result = await cur.execute(f"SELECT * FROM ag_graph WHERE graph_name = '{self.graph_name}';")  # type: ignore
            exists = await result.fetchone()
            if not exists:
                await cur.execute(f"SELECT create_graph('{self.graph_name}');")  # type: ignore
                return True
            return False

    async def adrop_graph(self) -> bool:
        async with self.__db.acursor() as cur:
            result = await cur.execute(f"SELECT * FROM ag_graph WHERE graph_name = '{self.graph_name}';")  # type: ignore
            exists = await result.fetchone()
            if exists:
                await cur.execute(f"SELECT drop_graph('{self.graph_name}', true);")  # type: ignore
                return True
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
        return None

    async def adelete_vertex(self, uri: str, label: str | None = None) -> bool:
        label_clause = f":{label}" if label else ""
        cypher = f"""
        MATCH (v{label_clause} {{uri: $uri}})
        DETACH DELETE v
        RETURN count(*) as deleted_count
        """
        results = await self.aexecute_cypher(cypher, {"uri": uri}, read_only=False)
        if results and results[0].get("deleted_count", 0) > 0:
            return True
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
        predicate_uri = f"cidoc:relationship/{relationship_type}"
        edge_props: dict[str, Any] = {"uri": predicate_uri}
        if properties:
            edge_props.update(properties)

        props_set = ", ".join([f"r.{k} = ${k}" for k in edge_props])

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
            "predicate_uri": predicate_uri,
        }
        params.update(edge_props)

        results = await self.aexecute_cypher(cypher, params, read_only=False)
        if results:
            row = results[0]
            return {
                "id": row.get("id"),
                "label": relationship_type,
                "uri": predicate_uri,
                "start_uri": start_uri,
                "end_uri": end_uri,
                "relationship_type": row.get("relationship_type"),
                **{k: v for k, v in edge_props.items() if k != "uri"},
            }
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
        results = await self.aexecute_cypher(
            cypher,
            {"start_uri": start_uri, "end_uri": end_uri},
            read_only=False,
        )
        if results and results[0].get("deleted_count", 0) > 0:
            return True
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
        return await self.ato_networkx(cypher, {"uri": start_uri})

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

        return await self.ato_networkx(cypher, {"start_uri": start_uri, "end_uri": end_uri})

    async def aexpand_context(
        self,
        entity_uri: str,
        max_hops: int = 2,
        direction: str = "both",
    ) -> dict[str, Any]:
        graph = await self.atraverse(entity_uri, max_hops=max_hops, direction=direction)

        context: dict[str, Any] = {
            "center_entity": entity_uri,
            "connected_entities": [],
            "paths": [],
        }

        for node_uri, data in graph.nodes(data=True):
            if node_uri != entity_uri:
                context["connected_entities"].append(
                    {
                        "uri": node_uri,
                        "name": data.get("name"),
                        "type": data.get("entity_type"),
                    },
                )

        for u, v, data in graph.edges(data=True):
            context["paths"].append(
                {
                    "start_uri": u,
                    "end_uri": v,
                    "relationship": data.get("relationship_type") or data.get("label"),
                },
            )

        return context

    async def afind_entity_paths(
        self,
        start_uri: str,
        end_uri: str,
        max_hops: int = 5,
    ) -> dict[str, list[dict[str, str | None]]]:
        graph = await self.afind_paths(start_uri, end_uri, max_hops)

        path_dict: dict[str, list[dict[str, str | None]]] = {"nodes": [], "edges": []}
        for node_uri, data in graph.nodes(data=True):
            path_dict["nodes"].append(
                {
                    "uri": node_uri,
                    "name": data.get("name"),
                    "type": data.get("entity_type"),
                },
            )
        for u, v, data in graph.edges(data=True):
            path_dict["edges"].append(
                {
                    "start_uri": u,
                    "end_uri": v,
                    "relationship": data.get("relationship_type") or data.get("label"),
                },
            )
        return path_dict

    async def afrom_networkx(self, graph: DiGraph) -> bool:
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

    async def ato_networkx(self, cypher: str, params: dict | None = None) -> DiGraph:

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

        rows = await self.aexecute_cypher(cypher, params, read_only=True)
        for row in rows:
            for x in row:
                if isinstance(x, Path):
                    add_path(x)
                elif isinstance(x, Edge):
                    add_edge_to_networkx(x)
                elif isinstance(x, Vertex):
                    add_node_to_networkx(x)
        return graph
