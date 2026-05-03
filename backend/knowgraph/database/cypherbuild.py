import math
from copy import deepcopy
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
    if isinstance(value, PatternBuilder):
        return value.build()
    if isinstance(value, ExpressionBuilder):
        return value.build()
    if isinstance(value, CypherBuilder):
        return value.build()
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
        clone = deepcopy(self)
        node_str = variable
        if label:
            node_str += f":{label}"
        if props:
            node_str += f" {_format_props(props)}"
        clone._patterns.append(f"({node_str})")
        return clone

    def rel(
        self,
        variable: str | None = None,
        label: str | None = None,
        props: dict[str, Any] | None = None,
        direction: Literal["->", "<-", "--"] = "--",
        length: str | None = None,
    ) -> Self:
        clone = deepcopy(self)
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
            clone._patterns.append(f"-{bracket}->")
        elif direction == "<-":
            clone._patterns.append(f"<-{bracket}-")
        else:
            clone._patterns.append(f"-{bracket}-")
        return clone

    def build(self) -> str:
        return "".join(self._patterns)

    def __str__(self) -> str:
        return self.build()

    def __rshift__(self, other):
        return self.rel(other, direction="->")

    def __lshift__(self, other):
        return self.rel(other, direction="<-")

    def __sub__(self, other):
        return self.rel(other, direction="--")

    def apply(self, pattern: PatternBuilder):
        clone = deepcopy(self)
        clone._patterns.extend(pattern._patterns)
        return clone


class ExpressionBuilder:  # noqa: PLW1641
    """Helper for building Cypher expressions with proper quoting and operator support."""

    def __init__(self) -> None:
        self._exprs = []

    def expr(self, value):
        self._exprs.append(_quote_value(value))
        return self

    def raw(self, value: str):
        self._exprs.append(value)

    def __add__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("+ " + _quote_value(other))
        return clone

    add_ = __add__

    def __sub__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("- " + _quote_value(other))
        return clone

    sub_ = __sub__

    def __mul__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("* " + _quote_value(other))
        return clone

    mul_ = __mul__

    def __eq__(self, other):  # pyright: ignore
        clone = deepcopy(self)
        clone._exprs.append("= " + _quote_value(other))
        return clone

    eq_ = __eq__

    def __ne__(self, other):  # pyright: ignore
        clone = deepcopy(self)
        clone._exprs.append("<> " + _quote_value(other))
        return clone

    ne_ = __ne__

    def __gt__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("> " + _quote_value(other))
        return clone

    gt_ = __gt__

    def __ge__(self, other):
        clone = deepcopy(self)
        clone._exprs.append(">= " + _quote_value(other))
        return clone

    ge_ = __ge__

    def __lt__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("< " + _quote_value(other))
        return clone

    lt_ = __lt__

    def __le__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("<= " + _quote_value(other))
        return clone

    le_ = __le__

    def __truediv__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("/ " + _quote_value(other))
        return clone

    div_ = __truediv__

    def __mod__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("% " + _quote_value(other))
        return clone

    mod_ = __mod__

    def __and__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("AND " + _quote_value(other))
        return clone

    and_ = __and__

    def __or__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("OR " + _quote_value(other))
        return clone

    or_ = __or__

    def __xor__(self, other):
        clone = deepcopy(self)
        clone._exprs.append("XOR " + _quote_value(other))
        return clone

    xor_ = __xor__

    def __invert__(self):
        clone = deepcopy(self)
        clone._exprs.insert(0, "NOT ")
        return clone

    not_ = __invert__

    def in_(self, other):
        clone = deepcopy(self)
        clone._exprs.append("IN " + _quote_value(other))
        return clone

    def is_(self, other):
        clone = deepcopy(self)
        if other is None:
            clone._exprs.append("IS NULL")
        else:
            clone._exprs.append("IS " + _quote_value(other))
        return clone

    def is_not(self, other):
        clone = deepcopy(self)
        if other is None:
            clone._exprs.append("IS NOT NULL")
        else:
            clone._exprs.append("IS NOT " + _quote_value(other))
        return clone

    def __iadd__(self, other):
        self._exprs.append("+ " + _quote_value(other))

    def __isub__(self, other):
        self._exprs.append("- " + _quote_value(other))

    def __imul__(self, other):
        self._exprs.append("* " + _quote_value(other))

    def __itruediv__(self, other):
        self._exprs.append("/ " + _quote_value(other))

    def __imod__(self, other):
        self._exprs.append("% " + _quote_value(other))

    def __iand__(self, other):
        self._exprs.append("AND " + _quote_value(other))

    def __ior__(self, other):
        self._exprs.append("OR " + _quote_value(other))

    def __ixor__(self, other):
        self._exprs.append("XOR " + _quote_value(other))

    def exists(self, pattern: str | PatternBuilder):
        clone = deepcopy(self)
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
        clone._exprs.append(f"EXISTS({pattern})")
        return clone

    def contains(self, other):
        clone = deepcopy(self)
        clone._exprs.append("CONTAINS " + _quote_value(other))
        return clone

    def startwith(self, other):
        clone = deepcopy(self)
        clone._exprs.append("STARTS WITH " + _quote_value(other))
        return clone

    def endwith(self, other):
        clone = deepcopy(self)
        clone._exprs.append("ENDS WITH " + _quote_value(other))
        return clone

    def regex(self, other):
        clone = deepcopy(self)
        clone._exprs.append("=~ " + _quote_value(other))
        return clone

    def build(self) -> str:
        return " ".join(self._exprs)

    def apply(self, expression: ExpressionBuilder):
        clone = deepcopy(self)
        clone._exprs.extend(expression._exprs)
        return clone

    def func(self, name: str, **args):
        clone = deepcopy(self)
        clone._exprs.append(f"{name}({_quote_value(args)[1:-1]})")
        return clone

    def __str__(self):
        return self.build()


class CypherBuilder:
    """Fluent builder for constructing Cypher queries (Apache AGE compatible)."""

    def __init__(self):
        self._clauses: list[str] = []
        self._params: dict[str, Any] = {}

    def match(self, pattern: str | PatternBuilder, optional: bool = False) -> Self:
        clone = deepcopy(self)
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
        if optional:
            clone._clauses.append(f"OPTIONAL MATCH {pattern}")
        else:
            clone._clauses.append(f"MATCH {pattern}")
        return clone

    def merge(self, pattern: str | PatternBuilder) -> Self:
        clone = deepcopy(self)
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
        clone._clauses.append(f"MERGE {pattern}")
        return clone

    def create(self, pattern: str | PatternBuilder) -> Self:
        clone = deepcopy(self)
        if isinstance(pattern, PatternBuilder):
            pattern = pattern.build()
        clone._clauses.append(f"CREATE {pattern}")
        return clone

    def set_(self, *items: str) -> Self:
        clone = deepcopy(self)
        clone._clauses.append(f"SET {', '.join(items)}")
        return clone

    def delete(self, *variables: str, detach: bool = False) -> Self:
        clone = deepcopy(self)
        if detach:
            clone._clauses.append(f"DETACH DELETE {', '.join(variables)}")
        else:
            clone._clauses.append(f"DELETE {', '.join(variables)}")
        return clone

    def unwind(self, expr: str, alias: str) -> Self:
        clone = deepcopy(self)
        clone._clauses.append(f"UNWIND {expr} AS {alias}")
        return clone

    def where(self, condition: str) -> Self:
        clone = deepcopy(self)
        clone._clauses.append(f"WHERE {condition}")
        return clone

    def limit(self, n: int) -> Self:
        clone = deepcopy(self)
        clone._clauses.append(f"LIMIT {n}")
        return clone

    def with_(self, *items: str | tuple[str, str]) -> Self:
        clone = deepcopy(self)
        converted_items = []
        for item in items:
            if isinstance(item, tuple):
                converted_items.append(f"{item[0]} AS {item[1]}")
            else:
                converted_items.append(item)
        clone._clauses.append(f"WITH {', '.join(converted_items)}")
        return clone

    def return_(self, *items: str | tuple[str, str]) -> Self:
        clone = deepcopy(self)
        converted_items = []
        for item in items:
            if isinstance(item, tuple):
                converted_items.append(f"{item[0]} AS {item[1]}")
            else:
                converted_items.append(item)
        clone._clauses.append(f"RETURN {', '.join(converted_items)}")
        return clone

    def union(self, other: CypherBuilder, union_all: bool = False) -> CypherBuilder:
        keyword = "UNION ALL" if union_all else "UNION"
        clone = deepcopy(self)
        clone._clauses.append(keyword)
        clone._clauses.extend(other._clauses)
        clone._params.update(other._params)
        return clone

    def raw(self, clause: str) -> Self:
        """Append a raw clause string directly."""
        clone = deepcopy(self)
        clone._clauses.append(clause)
        return clone

    def param(self, **kwargs: Any) -> Self:
        clone = deepcopy(self)
        clone._params.update(kwargs)
        return clone

    @property
    def params(self) -> dict[str, Any]:
        return dict(self._params)

    # -- Build --

    def build(self) -> str:
        cypher = " ".join(self._clauses)
        if self._params:
            cypher = _embed(cypher, self._params)
        return cypher

    def apply(self, cypher: CypherBuilder):
        clone = deepcopy(self)
        clone._clauses.extend(cypher._clauses)
        clone._params.update(cypher.params)
        return clone

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
