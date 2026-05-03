import math
from typing import Any, Literal, Self

from psycopg.sql import SQL, Composable, Identifier
from psycopg.sql import Literal as SQLiteral


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


def _is_var_ref(value: str) -> bool:
    """Check if a string should be treated as a Cypher variable/property reference."""
    if value.startswith("$"):
        return True
    if "." in value:
        return all(part.isidentifier() for part in value.split("."))
    return value.isidentifier()


def _format_props(props: dict[str, Any] | None) -> str:
    """Format inline properties like ``{key: $val, key2: 'literal'}``."""
    if not props:
        return ""
    parts = []
    for k, v in props.items():
        key = _quote_key(k)
        if isinstance(v, str) and _is_var_ref(v):
            parts.append(f"{key}: {v}")
        else:
            parts.append(f"{key}: {_quote_value(v)}")
    return "{" + ", ".join(parts) + "}"


def _embed(cypher: str, params: dict[str, Any]) -> str:
    param_keys = list(params.keys())
    param_keys.sort(key=len, reverse=True)
    for key in param_keys:
        placeholder = f"${key}"
        replacement = _quote_value(params[key])
        cypher = cypher.replace(placeholder, replacement)
    return cypher


class PatternBuilder:
    """Helper for building graph patterns (nodes, edges, paths) with proper quoting."""

    def __init__(self):
        self._patterns: list[str] = []

    def node(self, variable: str, label: str | None = None, props: dict[str, Any] | None = None) -> Self:
        node_str = variable
        if label:
            node_str += f":{label}"
        if props:
            node_str += f" {_format_props(props)}"
        self._patterns.append(f"({node_str})")
        return self

    def rel(
        self,
        variable: str | None = None,
        label: str | None = None,
        props: dict[str, Any] | None = None,
        direction: Literal["->", "<-", "--"] = "--",
        length: str | None = None,
    ) -> Self:
        inner = ""
        if variable:
            inner = variable
        if label:
            inner += f":{label}"
        if length:
            inner += f"*{length}"
        if props:
            inner += f" {_format_props(props)}"

        if inner.strip():
            bracket = f"[{inner}]"
        else:
            bracket = ""

        if direction == "->":
            self._patterns.append(f"-{bracket}->")
        elif direction == "<-":
            self._patterns.append(f"<-{bracket}-")
        else:
            self._patterns.append(f"-{bracket}-")
        return self

    def build(self) -> str:
        return "".join(self._patterns)

    def __str__(self) -> str:
        return self.build()


class CypherBuilder:
    """Fluent builder for constructing Cypher queries (Apache AGE compatible)."""

    def __init__(self):
        self._clauses: list[str] = []
        self._params: dict[str, Any] = {}

    def match(self, pattern: str | PatternBuilder, optional: bool = False) -> Self:
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
        if optional:
            self._clauses.append(f"OPTIONAL MATCH {pattern}")
        else:
            self._clauses.append(f"MATCH {pattern}")
        return self

    def merge(self, pattern: str | PatternBuilder) -> Self:
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
        self._clauses.append(f"MERGE {pattern}")
        return self

    def create(self, pattern: str | PatternBuilder) -> Self:
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
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

    def with_(self, *items: str | tuple[str, str]) -> Self:
        converted_items = []
        for item in items:
            if isinstance(item, tuple):
                converted_items.append(f"{item[0]} AS {item[1]}")
            else:
                converted_items.append(item)
        self._clauses.append(f"WITH {', '.join(converted_items)}")
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


def match(pattern: str | PatternBuilder) -> CypherBuilder:
    return CypherBuilder().match(pattern)


def merge(pattern: str | PatternBuilder) -> CypherBuilder:
    return CypherBuilder().merge(pattern)


def unwind(expr: str, alias: str) -> CypherBuilder:
    return CypherBuilder().unwind(expr, alias)


def create(pattern: str | PatternBuilder) -> CypherBuilder:
    return CypherBuilder().create(pattern)


def node(variable: str, label: str | None = None, props: dict[str, Any] | None = None) -> PatternBuilder:
    return PatternBuilder().node(variable, label, props)


def ref(name: str) -> str:
    return f"${name}"


def assign(prefix: str, props: dict[str, Any]) -> str:
    return ", ".join(f"{prefix}.{_quote_key(k)} = {ref(k)}" for k in props)


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
        graphName=SQLiteral(graph_name),
        cypher=SQLiteral(cypher),
        columns=cols,
    )
