import operator
from functools import reduce
from typing import Any

from age.models import Edge, Path, Vertex
from networkx import DiGraph

from knowgraph.database.cypherbuild import (
    CypherBuilder,
    _quote_key,
    build_cypher_stmt,
    expr,
    func,
    match,
    merge,
    node,
    unwind,
)
from knowgraph.database.database import DatabaseManager
from knowgraph.graph.schema import EntityType, get_entity_uri, parse_entity_uri

GRAPH_LABEL = "graph"


class AgeGraphManager:  # noqa: PLR0904
    def __init__(self, graph_name: str = GRAPH_LABEL, dbname: str | None = None):
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
        for node_key, data in graph.nodes(data=True):
            props = data.get("properties", {}) if isinstance(data.get("properties"), dict) else {}
            entity_type = data.get("entity_type") or props.get("entity_type")
            name = data.get("name") or props.get("name")
            node_uri: str | None = None
            if entity_type and name:
                try:
                    node_uri = get_entity_uri(EntityType(str(entity_type)), str(name))
                except ValueError:
                    node_uri = str(node_key)
            else:
                node_uri = str(node_key)
            node_data: dict[str, Any] = {"uri": node_uri, "entity_type": entity_type, "name": name}
            node_data.update({k: v for k, v in data.items() if k not in {"uri", "entity_type", "name", "properties"}})
            node_data.update({k: v for k, v in props.items() if k not in {"entity_type", "name"}})
            nodes.append(node_data)

        edges: list[dict[str, Any]] = []
        for u, v, data in graph.edges(data=True):
            start_data = graph.nodes[u]
            end_data = graph.nodes[v]
            start_uri = str(AgeGraphManager._node_props_to_uri(start_data) or u)
            end_uri = str(AgeGraphManager._node_props_to_uri(end_data) or v)
            edge_props = data.get("properties", {}) if isinstance(data.get("properties"), dict) else {}
            edge_data: dict[str, Any] = {"start_uri": start_uri, "end_uri": end_uri}
            edge_data.update({k: v for k, v in data.items() if k != "properties"})
            edge_data.update(edge_props)
            edges.append(edge_data)

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _uri_to_match_params(uri: str) -> tuple[str, str] | None:
        parsed = parse_entity_uri(uri)
        if parsed is None:
            return None
        entity_type, name = parsed
        return entity_type.value, name

    @staticmethod
    def _node_props_to_uri(data: dict[str, Any]) -> str | None:
        entity_type = data.get("entity_type")
        name = data.get("name")
        if not entity_type or not name:
            props = data.get("properties", {})
            if isinstance(props, dict):
                entity_type = entity_type or props.get("entity_type")
                name = name or props.get("name")
        if entity_type and name:
            try:
                return get_entity_uri(EntityType(str(entity_type)), str(name))
            except ValueError:
                pass
        return None

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
                await cur.execute(t"SELECT drop_graph({self.graph_name:s},true);")
                return True
            return False

    async def amupsert_vertex(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        entity_type = properties.get("entity_type")
        name = properties.get("name")
        if not entity_type or not name:
            uri = properties.get("uri")
            if uri:
                match_params = self._uri_to_match_params(uri)
                if match_params is None:
                    return None
                entity_type, name = match_params
            else:
                return None

        cypher = (
            merge(node("v", label, {"entity_type": "$entity_type", "name": "$name"}))
            .set_("v+=$props")
            .return_(
                ("id(v)", "id"),
                ("labels(v)", "labels"),
                ("v.entity_type", "entity_type"),
                ("v.name", "name"),
            )
        )
        results = await self.aexecute_cypher(
            cypher,
            read_only=False,
            params={
                "entity_type": str(entity_type),
                "name": str(name),
                "props": {k: v for k, v in properties.items() if k not in {"entity_type", "name", "uri"}},
            },
        )
        if results:
            row = results[0]
            vertex_uri = self._node_props_to_uri(row)
            return {
                "id": row.get("id"),
                "label": (row.get("labels") or [label])[0] if row.get("labels") else label,
                "uri": vertex_uri,
                "name": row.get("name"),
                "entity_type": row.get("entity_type"),
                **{k: v for k, v in properties.items() if k not in {"id", "entity_type", "name", "uri"}},
            }
        return None

    async def aget_vertex(
        self,
        uri: str,
        label: str | None = None,
    ) -> dict[str, Any] | None:
        match_params = self._uri_to_match_params(uri)
        if match_params is None:
            return None
        entity_type, name = match_params

        cypher = match(node("v", label, {"entity_type": "$entity_type", "name": "$name"})).return_(
            ("id(v)", "id"),
            ("labels(v)", "labels"),
            ("v.entity_type", "entity_type"),
            ("v.name", "name"),
            ("v.description", "description"),
        )
        results = await self.aexecute_cypher(
            cypher,
            params={"entity_type": entity_type, "name": name},
        )
        if results:
            row = results[0]
            vertex_uri = self._node_props_to_uri(row)
            return {
                "id": row.get("id"),
                "label": (row.get("labels") or [""])[0],
                "uri": vertex_uri,
                "name": row.get("name"),
                "entity_type": row.get("entity_type"),
                "description": row.get("description"),
            }
        return None

    async def adelete_vertex(self, uri: str, label: str | None = None) -> bool:
        match_params = self._uri_to_match_params(uri)
        if match_params is None:
            return False
        entity_type, name = match_params

        cypher = (
            match(node("v", label, {"entity_type": "$entity_type", "name": "$name"}))
            .delete("v", detach=True)
            .return_(("count(*)", "deleted_count"))
        )
        results = await self.aexecute_cypher(
            cypher,
            read_only=False,
            params={"entity_type": entity_type, "name": name},
        )
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
        start_match = self._uri_to_match_params(start_uri)
        end_match = self._uri_to_match_params(end_uri)
        if start_match is None or end_match is None:
            return None
        start_entity_type, start_name = start_match
        end_entity_type, end_name = end_match

        edge_props: dict[str, Any] = {}
        if properties:
            edge_props.update(properties)

        cypher = (
            match(node("s", start_label, {"entity_type": "$start_entity_type", "name": "$start_name"}))
            .match(node("e", end_label, {"entity_type": "$end_entity_type", "name": "$end_name"}))
            .merge(
                node("s").rel("r", relationship_type, direction="->").node("e"),
            )
            .set_(r={"relationship_type": "$relationship_type", **{k: f"${k}" for k in edge_props}})
            .return_(("id(r)", "id"), ("type(r)", "relationship_type"))
        )

        params: dict[str, Any] = {
            "start_entity_type": start_entity_type,
            "start_name": start_name,
            "end_entity_type": end_entity_type,
            "end_name": end_name,
            "relationship_type": relationship_type,
            **edge_props,
        }
        results = await self.aexecute_cypher(cypher, read_only=False, params=params)
        if results:
            row = results[0]
            return {
                "id": row.get("id"),
                "label": relationship_type,
                "uri": f"cidoc:relationship/{relationship_type}",
                "start_uri": start_uri,
                "end_uri": end_uri,
                "relationship_type": row.get("relationship_type"),
                **edge_props,
            }
        return None

    async def aget_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str | None = None,
    ) -> dict[str, Any] | None:
        start_match = self._uri_to_match_params(start_uri)
        end_match = self._uri_to_match_params(end_uri)
        if start_match is None or end_match is None:
            return None
        start_entity_type, start_name = start_match
        end_entity_type, end_name = end_match

        cypher = match(
            node("s", props={"entity_type": "$start_entity_type", "name": "$start_name"})
            .rel("r", relationship_type, direction="->")
            .node("e", props={"entity_type": "$end_entity_type", "name": "$end_name"}),
        ).return_(
            ("id(r)", "id"),
            ("type(r)", "relationship_type"),
            ("s.entity_type", "start_entity_type"),
            ("s.name", "start_name"),
            ("e.entity_type", "end_entity_type"),
            ("e.name", "end_name"),
        )
        results = await self.aexecute_cypher(
            cypher,
            params={
                "start_entity_type": start_entity_type,
                "start_name": start_name,
                "end_entity_type": end_entity_type,
                "end_name": end_name,
            },
        )
        if results:
            row = results[0]
            rel_type = row.get("relationship_type")
            start_computed_uri = self._node_props_to_uri(
                {"entity_type": row.get("start_entity_type"), "name": row.get("start_name")},
            )
            end_computed_uri = self._node_props_to_uri(
                {"entity_type": row.get("end_entity_type"), "name": row.get("end_name")},
            )
            return {
                "id": row.get("id"),
                "label": rel_type,
                "uri": f"cidoc:relationship/{rel_type}" if rel_type else None,
                "start_uri": start_computed_uri,
                "end_uri": end_computed_uri,
                "relationship_type": rel_type,
            }
        return None

    async def adelete_edge(
        self,
        start_uri: str,
        end_uri: str,
        relationship_type: str,
    ) -> bool:
        start_match = self._uri_to_match_params(start_uri)
        end_match = self._uri_to_match_params(end_uri)
        if start_match is None or end_match is None:
            return False
        start_entity_type, start_name = start_match
        end_entity_type, end_name = end_match

        cypher = (
            match(
                node("s", props={"entity_type": "$start_entity_type", "name": "$start_name"})
                .rel("r", relationship_type, direction="->")
                .node("e", props={"entity_type": "$end_entity_type", "name": "$end_name"}),
            )
            .delete("r")
            .return_("count(*) as deleted_count")
        )
        results = await self.aexecute_cypher(
            cypher,
            read_only=False,
            params={
                "start_entity_type": start_entity_type,
                "start_name": start_name,
                "end_entity_type": end_entity_type,
                "end_name": end_name,
            },
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
        match_params = self._uri_to_match_params(start_uri)
        if match_params is None:
            return DiGraph()
        entity_type, name = match_params

        if direction == "outbound":
            rel_dir = "->"
        elif direction == "inbound":
            rel_dir = "<-"
        else:
            rel_dir = "--"

        path_pattern = (
            node("start", props={"entity_type": "$entity_type", "name": "$name"})
            .rel("", length=f"1..{max_hops}", direction=rel_dir)
            .node("end")
        )
        cypher = match(f"path = {path_pattern}").return_("nodes(path) as nodes", "relationships(path) as edges")
        return await self.ato_networkx(cypher, params={"entity_type": entity_type, "name": name})

    async def atraverse_multi(
        self,
        uris: list[str],
        max_hops: int = 3,
        direction: str = "both",
    ) -> DiGraph:
        if not uris:
            return DiGraph()

        infos: list[dict[str, str]] = []
        for uri in uris:
            match_params = self._uri_to_match_params(uri)
            if match_params is not None:
                entity_type, name = match_params
                infos.append({"entity_type": entity_type, "name": name})
        if not infos:
            return DiGraph()

        if direction == "outbound":
            rel_dir = "->"
        elif direction == "inbound":
            rel_dir = "<-"
        else:
            rel_dir = "--"

        path_pattern = (
            node("start", props={"entity_type": "info.entity_type", "name": "info.name"})
            .rel("", length=f"1..{max_hops}", direction=rel_dir)
            .node("end")
        )
        cypher = (
            unwind("$infos", "info")
            .match(f"path = {path_pattern}")
            .return_(("nodes(path)", "nodes"), ("relationships(path)", "edges"))
        )
        return await self.ato_networkx(cypher, params={"infos": infos})

    async def afind_paths(
        self,
        start_uri: str,
        end_uri: str,
        max_hops: int = 5,
    ) -> DiGraph:
        start_match = self._uri_to_match_params(start_uri)
        end_match = self._uri_to_match_params(end_uri)
        if start_match is None or end_match is None:
            return DiGraph()
        start_entity_type, start_name = start_match
        end_entity_type, end_name = end_match

        path_pattern = (
            node("start", props={"entity_type": "$start_entity_type", "name": "$start_name"})
            .rel("", length=f"1..{max_hops}", direction="->")
            .node("end", props={"entity_type": "$end_entity_type", "name": "$end_name"})
        )
        cypher = match(f"path = shortestPath({path_pattern})").return_(
            ("nodes(path)", "nodes"),
            ("relationships(path)", "edges"),
        )
        return await self.ato_networkx(
            cypher,
            params={
                "start_entity_type": start_entity_type,
                "start_name": start_name,
                "end_entity_type": end_entity_type,
                "end_name": end_name,
            },
        )

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

        for node_key, data in graph.nodes(data=True):
            node_uri = self._node_props_to_uri(data) or str(node_key)
            if node_uri is None:
                continue
            props = data.get("properties", {}) if isinstance(data.get("properties"), dict) else {}
            if node_uri != entity_uri:
                context["connected_entities"].append(
                    {
                        "uri": node_uri,
                        "name": data.get("name") or props.get("name"),
                        "type": data.get("entity_type") or props.get("entity_type"),
                    },
                )

        for u, v, data in graph.edges(data=True):
            start_data = graph.nodes[u]
            end_data = graph.nodes[v]
            start_uri = self._node_props_to_uri(start_data) or str(u)
            end_uri = self._node_props_to_uri(end_data) or str(v)
            context["paths"].append(
                {
                    "start_uri": start_uri,
                    "end_uri": end_uri,
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
            node_uri = self._node_props_to_uri(data) or str(node_key)
            props = data.get("properties", {}) if isinstance(data.get("properties"), dict) else {}
            path_dict["nodes"].append(
                {
                    "uri": node_uri,
                    "name": data.get("name") or props.get("name"),
                    "type": data.get("entity_type") or props.get("entity_type"),
                },
            )
        for u, v, data in graph.edges(data=True):
            start_data = graph.nodes[u]
            end_data = graph.nodes[v]
            start_uri = self._node_props_to_uri(start_data) or str(u)
            end_uri = self._node_props_to_uri(end_data) or str(v)
            path_dict["edges"].append(
                {
                    "start_uri": start_uri,
                    "end_uri": end_uri,
                    "relationship": data.get("label"),
                },
            )
        return path_dict

    async def afrom_networkx(self, graph: DiGraph) -> bool:
        nodes_by_label: dict[str, list[dict[str, Any]]] = {}
        for node_uri, data in graph.nodes(data=True):
            label = data.get("label", "Entity")
            extra = data.get("properties", {})
            props_data = extra if isinstance(extra, dict) else {}
            entity_type = data.get("entity_type") or props_data.get("entity_type", "")
            name = data.get("name") or props_data.get("name", str(node_uri))

            if not entity_type:
                parsed = parse_entity_uri(str(node_uri))
                if parsed:
                    entity_type = parsed[0].value
                    name = parsed[1] if not data.get("name") and not props_data.get("name") else name

            node_props: dict[str, Any] = {"entity_type": entity_type, "name": name}

            for k, v in props_data.items():
                if v is not None and k not in node_props:
                    node_props[k] = v

            if data.get("description") is not None:
                node_props.setdefault("description", data["description"])

            nodes_by_label.setdefault(label, []).append(node_props)

        for label, nodes in nodes_by_label.items():
            cypher = (
                unwind("$nodes", "node")
                .merge(node("v", label, {"entity_type": "node.entity_type", "name": "node.name"}))
                .set_("v+=node")
            )
            await self.aexecute_cypher(cypher, read_only=False, params={"nodes": nodes})

        edges_by_type: dict[str, list[dict[str, Any]]] = {}
        for u, v, data in graph.edges(data=True):
            rel_type = data.get("label", "related_to")
            start_data = graph.nodes[u]
            end_data = graph.nodes[v]

            start_extra = start_data.get("properties", {})
            start_props = start_extra if isinstance(start_extra, dict) else {}
            end_extra = end_data.get("properties", {})
            end_props = end_extra if isinstance(end_extra, dict) else {}

            start_entity_type = start_data.get("entity_type") or start_props.get("entity_type", "")
            start_name = start_data.get("name") or start_props.get("name", str(u))
            end_entity_type = end_data.get("entity_type") or end_props.get("entity_type", "")
            end_name = end_data.get("name") or end_props.get("name", str(v))

            if not start_entity_type:
                parsed = parse_entity_uri(str(u))
                if parsed:
                    start_entity_type = parsed[0].value
                    start_name = parsed[1]
            if not end_entity_type:
                parsed = parse_entity_uri(str(v))
                if parsed:
                    end_entity_type = parsed[0].value
                    end_name = parsed[1]

            extra = data.get("properties", {})
            edge_props_data = extra if isinstance(extra, dict) else {}

            props: dict[str, Any] = {}
            for k, val in edge_props_data.items():
                if val is not None:
                    props[k] = val

            edges_by_type.setdefault(rel_type, []).append({
                "s_type": start_entity_type,
                "s_name": start_name,
                "e_type": end_entity_type,
                "e_name": end_name,
                "p": props,
            })

        for rel_type, edges in edges_by_type.items():
            first_keys = edges[0]["p"].keys()
            set_exprs = tuple(f"r.{_quote_key(k)}=edge.p.{_quote_key(k)}" for k in first_keys) if first_keys else ()
            cypher = (
                unwind("$edges", "edge")
                .match(node("s", props={"entity_type": "edge.s_type", "name": "edge.s_name"}))
                .match(node("e", props={"entity_type": "edge.e_type", "name": "edge.e_name"}))
                .merge(
                    node("s").rel("r", rel_type, direction="->").node("e"),
                )
            )
            if set_exprs:
                cypher = cypher.set_(*set_exprs)
            await self.aexecute_cypher(cypher, read_only=False, params={"edges": edges})

        return True

    async def ato_networkx(self, cypher: str | CypherBuilder, params: dict | None = None) -> DiGraph:

        graph = DiGraph()

        def add_node_to_networkx(node: Vertex):
            graph.add_node(node.id, label=node.label, properties=node.properties)

        def add_edge_to_networkx(edge: Edge):
            graph.add_edge(edge.start_id, edge.end_id, label=edge.label, properties=edge.properties)

        def add_path(path: Path):
            for x in path:
                if isinstance(x, Path):
                    add_path(x)
            for x in path:
                if isinstance(x, Vertex):
                    add_node_to_networkx(x)
            for x in path:
                if isinstance(x, Edge):
                    add_edge_to_networkx(x)

        rows = await self.aexecute_cypher(
            cypher,
            params=params,
            columns=None,
            read_only=True,
        )
        for row in rows:
            for value in row.values():
                if isinstance(value, Path):
                    add_path(value)
            for value in row.values():
                if isinstance(value, Vertex):
                    add_node_to_networkx(value)
            for value in row.values():
                if isinstance(value, Edge):
                    add_edge_to_networkx(value)

        return graph

    async def aget_all_edge_connections(self) -> list[dict[str, Any]]:
        cypher = match(node("s").rel("r", direction="->").node("o")).return_(
            ("type(r)", "relationship_type"),
            ("s.entity_type", "start_entity_type"),
            ("s.name", "subject_name"),
            ("o.entity_type", "end_entity_type"),
            ("o.name", "object_name"),
            ("r.description", "description"),
            ("r.connection_strength", "connection_strength"),
        )
        rows = await self.aexecute_cypher(cypher)
        for row in rows:
            rel_type = row.get("relationship_type")
            if rel_type:
                row["predicate_uri"] = f"cidoc:relationship/{rel_type}"
        return rows

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
            ("type(r)", "relationship_type"),
            ("s.entity_type", "start_entity_type"),
            ("s.name", "subject_name"),
            ("o.entity_type", "end_entity_type"),
            ("o.name", "object_name"),
            ("r.description", "description"),
            ("r.connection_strength", "connection_strength"),
        ).limit(limit)

        rows = await self.aexecute_cypher(builder, params=params)
        for row in rows:
            rel_type = row.get("relationship_type")
            if rel_type:
                row["predicate_uri"] = f"cidoc:relationship/{rel_type}"
        return rows

    async def aquery_edge_connections_by_entity_names(
        self,
        names: list[str],
    ) -> list[dict[str, Any]]:
        return_cols = (
            ("name", "query_name"),
            ("type(r)", "relationship_type"),
            ("s.entity_type", "start_entity_type"),
            ("s.name", "subject_name"),
            ("o.entity_type", "end_entity_type"),
            ("o.name", "object_name"),
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
        infos: list[dict[str, str]] = []
        for uri in uris:
            match_params = self._uri_to_match_params(uri)
            if match_params is not None:
                entity_type, name = match_params
                infos.append({"entity_type": entity_type, "name": name})
        if not infos:
            return []

        cypher = (
            unwind("$infos", "info")
            .match(node("v", props={"entity_type": "info.entity_type", "name": "info.name"}))
            .return_(
                ("v.entity_type", "entity_type"),
                ("v.name", "name"),
                ("id(v)", "id"),
                ("v.description", "description"),
            )
        )
        return await self.aexecute_cypher(cypher, params={"infos": infos})
