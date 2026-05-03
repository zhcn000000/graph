import math
from typing import Any, Self

from psycopg.sql import SQL, Composable, Identifier, Literal


def _quote_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return str(value)
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, (list, tuple)):
        items = ", ".join(_quote_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{_quote_key(k)}: {_quote_value(v)}" for k, v in value.items())
        return f"{{{pairs}}}"
    return _quote_value(str(value))


def _quote_key(key: object) -> str:
    if isinstance(key, str) and key.replace("_", "").isalnum():
        return key
    return _quote_value(key)


class CypherBuilder:
    """Fluent builder for constructing Cypher queries (Apache AGE compatible).

    Usage::

        cypher = (
            CypherBuilder()
            .match("(v:Artifact {uri: $uri})")
            .return_("v.uri as uri", "v.name as name")
            .param(uri="http://example.org/artifact/1")
        )
        result = await graph.aexecute_cypher(cypher)
    """

    def __init__(self):
        self._clauses: list[str] = []
        self._params: dict[str, Any] = {}

    # -- Clause builders --

    def match(self, pattern: str, optional: bool = False) -> Self:
        if optional:
            self._clauses.append(f"OPTIONAL MATCH {pattern}")
        else:
            self._clauses.append(f"MATCH {pattern}")
        return self

    def merge(self, pattern: str) -> Self:
        self._clauses.append(f"MERGE {pattern}")
        return self

    def create(self, pattern: str) -> Self:
        self._clauses.append(f"CREATE {pattern}")
        return self

    def set_(self, *items: str) -> Self:
        self._clauses.append(f"SET {', '.join(items)}")
        return self

    def delete(self, *variables: str, detach: bool = False) -> Self:
        if detach:
            self._clauses.append(f"DETACH DELETE {', '.join(variables)}")
        else:
            self._clauses.append(f"DELETE {', '.join(variables)}")
        return self

    def unwind(self, expr: str, alias: str) -> Self:
        self._clauses.append(f"UNWIND {expr} AS {alias}")
        return self

    def where(self, condition: str) -> Self:
        self._clauses.append(f"WHERE {condition}")
        return self

    def limit(self, n: int) -> Self:
        self._clauses.append(f"LIMIT {n}")
        return self

    def return_(self, *items: str | tuple[str, str]) -> Self:
        converted_items = []
        for item in items:
            if isinstance(item, tuple):
                converted_items.append(f"{item[0]} AS {item[1]}")
            else:
                converted_items.append(item)
        self._clauses.append(f"RETURN {', '.join(converted_items)}")
        return self

    def union(self, other: CypherBuilder, union_all: bool = False) -> CypherBuilder:
        keyword = "UNION ALL" if union_all else "UNION"
        self._clauses.append(keyword)
        self._clauses.extend(other._clauses)
        self._params.update(other._params)
        return self

    def raw(self, clause: str) -> Self:
        """Append a raw clause string directly."""
        self._clauses.append(clause)
        return self

    # -- Param helpers --

    def param(self, **kwargs: Any) -> Self:
        self._params.update(kwargs)
        return self

    @property
    def params(self) -> dict[str, Any]:
        return dict(self._params)

    # -- Build --

    def build(self) -> str:
        cypher = " ".join(self._clauses)
        if self._params:
            cypher = _embed(cypher, self._params)
        return cypher

    def __str__(self) -> str:
        return self.build()

    # -- Static helpers --

    @staticmethod
    def ref(name: str) -> str:
        """Build a parameter reference like ``$name``."""
        return f"${name}"

    @staticmethod
    def val(value: Any) -> str:
        """Quote a value for inline use in Cypher."""
        return _quote_value(value)

    @staticmethod
    def key(value: Any) -> str:
        """Quote a property key for use in Cypher."""
        return _quote_key(value)

    @staticmethod
    def props(props: dict[str, Any] | None) -> str:
        """Build inline properties like ``{key: $val, key2: 'literal'}``."""
        if not props:
            return ""
        parts = []
        for k, v in props.items():
            key = _quote_key(k)
            if isinstance(v, str) and v.startswith("$"):
                parts.append(f"{key}: {v}")
            else:
                parts.append(f"{key}: {_quote_value(v)}")
        return "{" + ", ".join(parts) + "}"

    @staticmethod
    def assign(prefix: str, props: dict[str, Any]) -> str:
        """Build SET-style assignments like ``r.k = $k, r.v = $v``."""
        return ", ".join(f"{prefix}.{_quote_key(k)} = {CypherBuilder.ref(k)}" for k in props)

    @staticmethod
    def label_opt(label: str | None) -> str:
        """Build optional label clause like ``:Label`` or empty string."""
        return f":{label}" if label else ""

    @staticmethod
    def node(variable: str, label: str | None = None, props: dict[str, Any] | None = None) -> str:
        """Build a node pattern like ``(v:Label {key: $val})``."""
        lbl = f":{label}" if label else ""
        prp = CypherBuilder.props(props)
        return f"({variable}{lbl} {prp})" if prp else f"({variable}{lbl})"


def match(pattern: str) -> CypherBuilder:
    return CypherBuilder().match(pattern)


def merge(pattern: str) -> CypherBuilder:
    return CypherBuilder().merge(pattern)


def unwind(expr: str, alias: str) -> CypherBuilder:
    return CypherBuilder().unwind(expr, alias)


def create(pattern: str) -> CypherBuilder:
    return CypherBuilder().create(pattern)


def _embed(cypher: str, params: dict[str, Any]) -> str:
    param_keys = list(params.keys())
    param_keys.sort(key=len, reverse=True)
    for key in param_keys:
        placeholder = f"${key}"
        replacement = _quote_value(params[key])
        cypher = cypher.replace(placeholder, replacement)
    return cypher


def build_cypher_stmt(
    graph_name: str,
    cypher: str | CypherBuilder,
    columns: list[str | tuple[str, str]] | None = None,
    params: dict[str, Any] | None = None,
) -> Composable:
    """Build the ``SELECT * FROM cypher(...) AS (columns)`` SQL wrapper."""
    if columns:
        builded_columns: list[str] = []
        for col in columns:
            if isinstance(col, tuple):
                builded_columns.append(f"{col[0]} {col[1]}")
            else:
                builded_columns.append(f"{col} agtype")
        col_parts: list[Composable] = []
        for raw_col in builded_columns:
            col = raw_col.strip()
            if not col:
                continue
            if " " in col:
                name, type_name = col.split(" ", 1)
                col_parts.append(SQL("{} {}").format(Identifier(name), Identifier(type_name)))
            else:
                col_parts.append(SQL("{} agtype").format(Identifier(col)))
        cols: Composable = SQL(", ").join(col_parts)
    else:
        cols = SQL("result agtype")
    if isinstance(cypher, CypherBuilder):
        if params:
            cypher = cypher.param(**params)
        cypher = cypher.build()

    return SQL("SELECT * FROM cypher({graphName}, {cypher}) AS ({columns})").format(
        graphName=Literal(graph_name),
        cypher=Literal(cypher),
        columns=cols,
    )
