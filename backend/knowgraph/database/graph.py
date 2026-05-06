import operator
from functools import reduce
from typing import Any

from age.models import Edge, Path, Vertex
from networkx import DiGraph

from knowgraph.database.cypherbuild import (
    CypherBuilder,
    build_cypher_stmt,
    expr,
    func,
    match,
    merge,
    node,
    unwind,
)
from knowgraph.database.database import DatabaseManager
from knowgraph.utils.environments import POSTGRES_DB

GRAPH_LABEL = "graph"


class AgeGraphManager:  # noqa: PLR0904
    def __init__(self, graph_name: str = GRAPH_LABEL, dbname: str = POSTGRES_DB):
        self.graph_name = graph_name
        self.__db = DatabaseManager(dbname)

    async def aexecute_cypher(
        self,
        cypher: str | CypherBuilder,
        params: dict[str, Any] | None = None,
        columns: list[str | tuple[str, str]] | None = None,
        read_only: bool = True,
    ) -> list[dict[str, Any]]:

        stmt = build_cypher_stmt(self.graph_name, cypher, columns, params)

        async with self.__db.acursor(read_only=read_only, autocommit=read_only) as cur:
            result = await cur.execute(stmt)
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
            result = await cur.execute(t"SELECT * FROM ag_catalog.ag_graph WHERE name = {self.graph_name:s}")
            exists = await result.fetchone()
            if not exists:
                await cur.execute(t"SELECT create_graph({self.graph_name:s});")
                return True
            return False

    async def adrop_graph(self) -> bool:
        async with self.__db.acursor() as cur:
            result = await cur.execute(t"SELECT * FROM ag_catalog.ag_graph WHERE name = {self.graph_name:s}")
            exists = await result.fetchone()
            if exists:
                await cur.execute(t"SELECT drop_graph({self.graph_name:s});")
                return True
            return False

    async def amupsert_vertex(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        if "uri" not in properties:
            return None

        cypher = (
            merge(node("v", label, {"uri": "$uri"}))
            .set_("v+=$props")
            .return_(
                ("id(v)", "id"),
                ("labels(v)", "labels"),
                ("v.uri", "uri"),
                ("v.name", "name"),
                ("v.entity_type", "entity_type"),
            )
        )
        results = await self.aexecute_cypher(
            cypher,
            read_only=False,
            params={"uri": properties["uri"], "props": {k: v for k, v in properties.items() if k != "uri"}},
        )
        if results:
            row = results[0]
            return {
                "id": row.get("id"),
                "label": (row.get("labels") or [label])[0] if row.get("labels") else label,
                "uri": row.get("uri"),
                "name": row.get("name"),
                "entity_type": row.get("entity_type"),
                **{k: v for k, v in properties.items() if k not in {"id", "uri", "name", "entity_type"}},
            }
        return None

    async def aget_vertex(
        self,
        uri: str,
        label: str | None = None,
    ) -> dict[str, Any] | None:
        cypher = match(node("v", label, {"uri": "$uri"})).return_(
            ("id(v)", "id"),
            ("labels(v)", "labels"),
            ("v.uri", "uri"),
            ("v.name", "name"),
            ("v.entity_type", "entity_type"),
            ("v.description", "description"),
        )
        results = await self.aexecute_cypher(cypher, params={"uri": uri})
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
        cypher = (
            match(node("v", label, {"uri": "$uri"})).delete("v", detach=True).return_(("count(*)", "deleted_count"))
        )
        results = await self.aexecute_cypher(cypher, read_only=False, params={"uri": uri})
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

        cypher = (
            match(node("s", start_label, {"uri": "$start_uri"}))
            .match(node("e", end_label, {"uri": "$end_uri"}))
            .merge(
                node("s").rel("r", relationship_type, {"uri": "$predicate_uri"}, direction="->").node("e"),
            )
            .set_(r={key: f"${value}" for key, value in edge_props.items()})
            .return_(("id(r)", "id"), ("r.uri", "uri"), ("type(r)", "relationship_type"))
        )

        results = await self.aexecute_cypher(
            cypher,
            read_only=False,
            params={"start_uri": start_uri, "end_uri": end_uri, "predicate_uri": predicate_uri, **edge_props},
        )
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
        cypher = match(
            node("s", props={"uri": "$start_uri"})
            .rel("r", relationship_type, direction="->")
            .node("e", props={"uri": "$end_uri"}),
        ).return_(
            ("id(r)", "id"),
            ("r.uri", "uri"),
            ("type(r)", "relationship_type"),
            ("s.uri", "start_uri"),
            ("e.uri", "end_uri"),
        )
        results = await self.aexecute_cypher(cypher, params={"start_uri": start_uri, "end_uri": end_uri})
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
        cypher = (
            match(
                node("s", props={"uri": "$start_uri"})
                .rel("r", relationship_type, direction="->")
                .node("e", props={"uri": "$end_uri"}),
            )
            .delete("r")
            .return_("count(*) as deleted_count")
        )
        results = await self.aexecute_cypher(
            cypher, read_only=False, params={"start_uri": start_uri, "end_uri": end_uri}
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
            rel_dir = "->"
        elif direction == "inbound":
            rel_dir = "<-"
        else:
            rel_dir = "--"

        path_pattern = (
            node("start", props={"uri": "$uri"}).rel("", length=f"1..{max_hops}", direction=rel_dir).node("end")
        )
        cypher = match(f"path = {path_pattern}").return_("nodes(path) as nodes", "relationships(path) as edges")
        return await self.ato_networkx(cypher, params={"uri": start_uri})

    async def atraverse_multi(
        self,
        uris: list[str],
        max_hops: int = 3,
        direction: str = "both",
    ) -> DiGraph:
        if not uris:
            return DiGraph()
        if direction == "outbound":
            rel_dir = "->"
        elif direction == "inbound":
            rel_dir = "<-"
        else:
            rel_dir = "--"

        path_pattern = (
            node("start", props={"uri": "uri"}).rel("", length=f"1..{max_hops}", direction=rel_dir).node("end")
        )
        cypher = (
            unwind("$uris", "uri")
            .match(f"path = {path_pattern}")
            .return_(("nodes(path)", "nodes"), ("relationships(path)", "edges"))
        )
        return await self.ato_networkx(cypher, params={"uris": uris})

    async def afind_paths(
        self,
        start_uri: str,
        end_uri: str,
        max_hops: int = 5,
    ) -> DiGraph:
        path_pattern = (
            node("start", props={"uri": "$start_uri"})
            .rel("", length=f"1..{max_hops}", direction="->")
            .node("end", props={"uri": "$end_uri"})
        )
        cypher = match(f"path = shortestPath({path_pattern})").return_(
            ("nodes(path)", "nodes"), ("relationships(path)", "edges")
        )
        return await self.ato_networkx(cypher, params={"start_uri": start_uri, "end_uri": end_uri})

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

        for _, data in graph.nodes(data=True):
            node_uri = data.get("uri")
            if node_uri is None:
                continue
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
                    "start_uri": graph.nodes[u].get("uri", u),
                    "end_uri": graph.nodes[v].get("uri", v),
                    "relationship": data.get("label"),
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
        for node_key, data in graph.nodes(data=True):
            path_dict["nodes"].append(
                {
                    "uri": data.get("uri", node_key),
                    "name": data.get("name"),
                    "type": data.get("entity_type"),
                },
            )
        for u, v, data in graph.edges(data=True):
            path_dict["edges"].append(
                {
                    "start_uri": graph.nodes[u].get("uri", u),
                    "end_uri": graph.nodes[v].get("uri", v),
                    "relationship": data.get("label"),
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
            cypher = unwind("$nodes", "node").merge(node("v", label, {"uri": "node.uri"})).set_("v+=node")
            await self.aexecute_cypher(cypher, read_only=False, params={"nodes": nodes})

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
            cypher = (
                unwind("$edges", "edge")
                .match(node("s", props={"uri": "edge.s"}))
                .match(node("e", props={"uri": "edge.e"}))
                .merge(
                    node("s").rel("r", rel_type, {"uri": "edge.p.uri"}, direction="->").node("e"),
                )
                .set_("r+=edge.p")
            )
            await self.aexecute_cypher(cypher, read_only=False, params={"edges": edges})

        return True

    async def ato_networkx(self, cypher: str | CypherBuilder, params: dict | None = None) -> DiGraph:

        graph = DiGraph()

        def add_node_to_networkx(node):
            attrs = {"label": node.label}
            if node.properties:
                attrs.update(node.properties)
            graph.add_node(node.id, **attrs)

        def add_edge_to_networkx(edge):
            graph.add_edge(edge.start_id, edge.end_id, label=edge.label, properties=edge.properties)

        def add_path(path):
            for x in path:
                if isinstance(x, Path):
                    add_path(x)
                elif isinstance(x, Vertex):
                    add_node_to_networkx(x)
                elif isinstance(x, Edge):
                    add_edge_to_networkx(x)

        rows = await self.aexecute_cypher(
            cypher, params=params, columns=["nodes agtype", "edges agtype"], read_only=True
        )
        for row in rows:
            for value in row.values():
                if isinstance(value, Path):
                    add_path(value)
                elif isinstance(value, Edge):
                    add_edge_to_networkx(value)
                elif isinstance(value, Vertex):
                    add_node_to_networkx(value)
        return graph

    async def aget_all_edge_connections(self) -> list[dict[str, Any]]:
        cypher = match(node("s").rel("r", direction="->").node("o")).return_(
            ("r.uri", "predicate_uri"),
            ("type(r)", "relationship_type"),
            ("startNode(r).uri", "start_node_uri"),
            ("startNode(r).name", "subject_name"),
            ("endNode(r).uri", "end_node_uri"),
            ("endNode(r).name", "object_name"),
            ("r.description", "description"),
            ("r.connection_strength", "connection_strength"),
        )
        return await self.aexecute_cypher(cypher)

    async def aquery_edge_connections(
        self,
        subject_name: str | None = None,
        predicate: str | None = None,
        object_name: str | None = None,
        description: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions: list = []
        builder = match(node("s").rel("r", direction="->").node("o"))
        params = {}

        if subject_name:
            conditions.append(expr(func().startNode("r").name).contains("$subject_name"))
            params["subject_name"] = subject_name
        if predicate:
            conditions.append(expr(func().type("r")) == ("$predicate"))
            params["predicate"] = predicate
        if object_name:
            conditions.append(expr(func().endNode("r").name).contains("$object_name"))
            params["object_name"] = object_name
        if description:
            conditions.append(expr(func().r.description).contains("$description"))
            params["description"] = description

        if conditions:
            builder = builder.where(reduce(operator.and_, conditions))

        builder = builder.return_(
            ("r.uri", "predicate_uri"),
            ("type(r)", "relationship_type"),
            ("startNode(r).uri", "start_node_uri"),
            ("startNode(r).name", "subject_name"),
            ("endNode(r).uri", "end_node_uri"),
            ("endNode(r).name", "object_name"),
            ("r.description", "description"),
            ("r.connection_strength", "connection_strength"),
        ).limit(limit)

        return await self.aexecute_cypher(builder, params=params)

    async def aquery_edge_connections_by_entity_names(
        self,
        names: list[str],
    ) -> list[dict[str, Any]]:
        return_cols = (
            ("name", "query_name"),
            ("type(r)", "relationship_type"),
            ("startNode(r).uri", "start_node_uri"),
            ("startNode(r).name", "subject_name"),
            ("endNode(r).uri", "end_node_uri"),
            ("endNode(r).name", "object_name"),
            ("r.description", "description"),
            ("r.connection_strength", "connection_strength"),
        )

        edge_pattern = node("s").rel("r", direction="->").node("o")

        sub1 = (
            unwind("$names", "name")
            .match(edge_pattern)
            .where(expr(func().startNode("r").name).contains(func().name))
            .return_(*return_cols)
        )
        sub2 = (
            unwind("$names", "name")
            .match(edge_pattern)
            .where(expr(func().endNode("r").name).contains(func().name))
            .return_(*return_cols)
        )

        return await self.aexecute_cypher(sub1.union(sub2, union_all=True), params={"names": names})

    async def aget_vertices_by_uris(self, uris: list[str]) -> list[dict[str, Any]]:
        cypher = (
            unwind("$uris", "uri")
            .match(node("v", props={"uri": "uri"}))
            .return_(
                ("v.uri", "uri"),
                ("id(v)", "id"),
                ("v.name", "name"),
                ("v.entity_type", "entity_type"),
            )
        )
        return await self.aexecute_cypher(cypher, params={"uris": uris})
