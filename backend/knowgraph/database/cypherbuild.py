import logging
import math
from abc import ABC, abstractmethod
from copy import deepcopy
from string.templatelib import Template
from typing import Any, Literal, Self


def _quote_value(value: Any) -> str:
    if value is None:
        return "NULL"
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
        if _is_var_ref(value):
            return value
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, (list, tuple)):
        items = ", ".join(_quote_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{_quote_key(k)}: {_quote_value(v)}" for k, v in value.items())
        return f"{{{pairs}}}"
    if isinstance(value, BuilderBase):
        return value.build()
    return _quote_value(str(value))


def _quote_param_value(value: Any) -> str:
    """Quote a value as a Cypher literal (parameter embedding, no variable refs)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _quote_value(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, (list, tuple)):
        items = ", ".join(_quote_param_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{_quote_key(k)}: {_quote_param_value(v)}" for k, v in value.items())
        return f"{{{pairs}}}"
    if isinstance(value, BuilderBase):
        return value.build()
    return _quote_param_value(str(value))


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


class BuilderBase(ABC):
    """Base class for builders, providing common utilities."""

    @abstractmethod
    def build(self) -> str:
        """Build the final string representation."""
        raise NotImplementedError

    def __str__(self) -> str:
        return self.build()


class PatternBuilder(BuilderBase):
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

    def apply(self, pattern: PatternBuilder):
        clone = deepcopy(self)
        clone._patterns.extend(pattern._patterns)
        return clone

    def __rshift__(self, other):
        return self.rel(label=other, direction="->")

    def __lshift__(self, other):
        return self.rel(label=other, direction="<-")

    def __sub__(self, other):
        return self.rel(label=other, direction="--")


class FunctionBuilder(BuilderBase):
    """Helper for building Cypher function calls with proper quoting."""

    def __init__(self) -> None:
        self._name = None
        self._props: list[str] = []

    def func(self, name) -> Self:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"{type(self).__name__} object has no attribute '{name}'")
        clone = deepcopy(self)
        if clone._name:
            clone._props.append(clone._name)
        clone._name = name
        return clone

    def call(self, *args: Any, **kwargs: Any) -> Self:
        clone = deepcopy(self)
        all_args = [_quote_value(arg) for arg in args]
        for k, v in kwargs.items():
            all_args.append(f"{_quote_key(k)}: {_quote_value(v)}")
        args_str = ", ".join(all_args)
        if not clone._name:
            raise ValueError("Function name is missing; use function.<name>(...).")
        clone._props.append(f"{clone._name}({args_str})")
        clone._name = None
        return clone

    def build(self) -> str:
        if self._name:
            self._props.append(self._name)
            self._name = None

        result = ""
        for prop in self._props:
            result += f".{prop}"
        return result.removeprefix(".")

    __getattr__ = func
    __call__ = call


class ExpressionBuilder(BuilderBase):  # noqa: PLW1641
    """Helper for building Cypher expressions with proper quoting and operator support."""

    def __init__(self) -> None:
        self._exprs = []

    def expr(self, value: str | FunctionBuilder) -> Self:
        clone = deepcopy(self)
        clone._exprs = [str(value)]
        return clone

    def raw(self, value: str):
        clone = deepcopy(self)
        clone._exprs.append(value)
        return clone

    def op(self, operator: str, other):
        clone = deepcopy(self)
        clone._exprs.append(operator)
        if isinstance(other, ExpressionBuilder):
            clone._exprs.extend(other._exprs)
        else:
            clone._exprs.append(_quote_value(other))
        return clone

    def add_(self, other):
        return self.op("+", other)

    def sub_(self, other):
        return self.op("-", other)

    def mul_(self, other):
        return self.op("*", other)

    def eq_(self, other):  # pyright: ignore
        return self.op("=", other)

    def ne_(self, other):  # pyright: ignore
        return self.op("<>", other)

    def gt_(self, other):
        return self.op(">", other)

    def ge_(self, other):
        return self.op(">=", other)

    def lt_(self, other):
        return self.op("<", other)

    def le_(self, other):
        return self.op("<=", other)

    def div_(self, other):
        return self.op("/", other)

    def mod_(self, other):
        return self.op("%", other)

    def and_(self, other):
        return self.op("AND", other)

    def or_(self, other):
        return self.op("OR", other)

    def xor_(self, other):
        return self.op("XOR", other)

    def in_(self, other):
        return self.op("IN", other)

    def is_(self, other):
        return self.op("IS", other)

    def is_not(self, other):
        return self.op("IS NOT", other)

    def as_(self, alias: str):
        clone = deepcopy(self)
        clone._exprs.append(f"AS {alias}")
        return clone

    def not_(self):
        clone = deepcopy(self)
        clone._exprs.insert(0, "NOT")
        return clone

    def __iadd__(self, other):
        self._exprs.append("+ " + _quote_value(other))
        return self

    def __isub__(self, other):
        self._exprs.append("- " + _quote_value(other))
        return self

    def __imul__(self, other):
        self._exprs.append("* " + _quote_value(other))
        return self

    def __itruediv__(self, other):
        self._exprs.append("/ " + _quote_value(other))
        return self

    def __imod__(self, other):
        self._exprs.append("% " + _quote_value(other))
        return self

    def __iand__(self, other):
        self._exprs.append("AND " + _quote_value(other))
        return self

    def __ior__(self, other):
        self._exprs.append("OR " + _quote_value(other))
        return self

    def __ixor__(self, other):
        self._exprs.append("XOR " + _quote_value(other))
        return self

    def exists(self, pattern: str | PatternBuilder):
        clone = deepcopy(self)
        if isinstance(pattern, BuilderBase):
            pattern = pattern.build()
        clone._exprs.append(f"EXISTS({pattern})")
        return clone

    def contains(self, other):
        return self.op("CONTAINS", other)

    def startwith(self, other):
        return self.op("STARTS WITH", other)

    def endwith(self, other):
        return self.op("ENDS WITH", other)

    def regex(self, other):
        return self.op("=~", other)

    def build(self) -> str:
        return " ".join(self._exprs)

    def apply(self, expression: ExpressionBuilder):
        clone = deepcopy(self)
        clone._exprs.extend(expression._exprs)
        return clone

    __add__ = add_
    __sub__ = sub_
    __mul__ = mul_
    __truediv__ = div_
    __floordiv__ = div_
    __mod__ = mod_
    __eq__ = eq_  # pyright: ignore
    __ne__ = ne_  # pyright: ignore
    __gt__ = gt_
    __ge__ = ge_
    __lt__ = lt_
    __le__ = le_
    __and__ = and_
    __or__ = or_
    __xor__ = xor_
    __invert__ = not_
    __ifloordiv__ = __itruediv__


class CypherBuilder(BuilderBase):
    """Fluent builder for constructing Cypher queries (Apache AGE compatible)."""

    def __init__(self):
        self._clauses: list[str] = []

    def match(self, pattern: str | PatternBuilder, optional: bool = False) -> Self:
        clone = deepcopy(self)
        if isinstance(pattern, BuilderBase):
            pattern = pattern.build()
        if optional:
            clone._clauses.append(f"OPTIONAL MATCH {pattern}")
        else:
            clone._clauses.append(f"MATCH {pattern}")
        return clone

    def merge(self, pattern: str | PatternBuilder) -> Self:
        clone = deepcopy(self)
        if isinstance(pattern, BuilderBase):
            pattern = pattern.build()
        clone._clauses.append(f"MERGE {pattern}")
        return clone

    def create(self, pattern: str | PatternBuilder) -> Self:
        clone = deepcopy(self)
        if isinstance(pattern, BuilderBase):
            pattern = pattern.build()
        clone._clauses.append(f"CREATE {pattern}")
        return clone

    def set_(self, *args, **kwargs) -> Self:
        clone = deepcopy(self)
        set_args = ""
        if args:
            set_args = ", ".join(args)
        if kwargs:
            if not set_args.endswith(", "):
                set_args += ", "
            set_args += ", ".join(f"{_quote_key(k)} = {_quote_value(v)}" for k, v in kwargs.items())
        if set_args:
            clone._clauses.append(f"SET {set_args}")
        return clone

    def delete(self, *variables: str, detach: bool = False) -> Self:
        clone = deepcopy(self)
        if detach:
            clone._clauses.append(f"DETACH DELETE {', '.join(variables)}")
        else:
            clone._clauses.append(f"DELETE {', '.join(variables)}")
        return clone

    def unwind(self, expr: str | ExpressionBuilder, alias: str) -> Self:
        clone = deepcopy(self)
        if isinstance(expr, BuilderBase):
            expr = expr.build()
        clone._clauses.append(f"UNWIND {expr} AS {alias}")
        return clone

    def where(self, condition: str | ExpressionBuilder) -> Self:
        clone = deepcopy(self)
        if isinstance(condition, BuilderBase):
            condition = condition.build()
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

    def return_(
        self,
        *items: str | ExpressionBuilder | tuple[str | ExpressionBuilder, str | ExpressionBuilder],
    ) -> Self:
        clone = deepcopy(self)
        converted_items = []
        for item in items:
            if isinstance(item, tuple):
                item_0 = item[0].build() if isinstance(item[0], BuilderBase) else item[0]
                item_1 = item[1].build() if isinstance(item[1], BuilderBase) else item[1]
                converted_items.append(f"{item_0} AS {item_1}")
            else:
                item_0 = item.build() if isinstance(item, BuilderBase) else item
                converted_items.append(item_0)
        clone._clauses.append(f"RETURN {', '.join(converted_items)}")
        return clone

    def union(self, other: CypherBuilder, union_all: bool = False) -> CypherBuilder:
        keyword = "UNION ALL" if union_all else "UNION"
        clone = deepcopy(self)
        clone._clauses.append(keyword)
        clone._clauses.extend(other._clauses)
        return clone

    def raw(self, clause: str) -> Self:
        """Append a raw clause string directly."""
        clone = deepcopy(self)
        clone._clauses.append(clause)
        return clone

    def build(self) -> str:
        cypher = " ".join(self._clauses)
        return cypher

    def apply(self, cypher: CypherBuilder):
        clone = deepcopy(self)
        clone._clauses.extend(cypher._clauses)
        return clone


def match(pattern: str | PatternBuilder) -> CypherBuilder:
    return CypherBuilder().match(pattern)


def merge(pattern: str | PatternBuilder) -> CypherBuilder:
    return CypherBuilder().merge(pattern)


def unwind(expr: str | ExpressionBuilder, alias: str) -> CypherBuilder:
    return CypherBuilder().unwind(expr, alias)


def create(pattern: str | PatternBuilder) -> CypherBuilder:
    return CypherBuilder().create(pattern)


def node(variable: str, label: str | None = None, props: dict[str, Any] | None = None) -> PatternBuilder:
    return PatternBuilder().node(variable, label, props)


def func(name: str | None = None) -> FunctionBuilder:
    if name is None:
        return FunctionBuilder()
    return FunctionBuilder().func(name)


def expr(value: str | FunctionBuilder) -> ExpressionBuilder:
    return ExpressionBuilder().expr(value)


def build_cypher_stmt(
    graph_name: str,
    cypher: str | CypherBuilder,
    columns: list[str | tuple[str, str]] | None = None,
    params: dict[str, Any] | None = None,
) -> Template:
    """Build the ``SELECT * FROM cypher(...) AS (columns)`` SQL wrapper."""
    if columns:
        builded_columns: list[str] = []
        for col in columns:
            if isinstance(col, tuple):
                builded_columns.append(f"{col[0]} {col[1]}")
            elif " " in col:
                builded_columns.append(col)
            else:
                builded_columns.append(f"{col} agtype")
        col_parts: list[Template] = []
        for raw_col in builded_columns:
            col = raw_col.strip()
            if not col:
                continue
            if " " in col:
                name, type_name = col.split(" ", 1)
                col_parts.append(t"{name:i} {type_name:i}")
            else:
                col_parts.append(t"{col:i} agtype")
        cols = col_parts[0]
        for col in col_parts[1:]:
            cols += t", " + col

    else:
        cols = t"result agtype"
    if isinstance(cypher, CypherBuilder):
        cypher = cypher.build()

    if params:
        for param_name in sorted(params.keys(), key=len, reverse=True):
            placeholder = f"${param_name}"
            if placeholder in cypher:
                cypher = cypher.replace(placeholder, _quote_param_value(params[param_name]))  # type: ignore
    logging.info("Built Cypher: %s", cypher)
    # cypher(name,cstring,agtype)
    final = t"SELECT * FROM cypher({graph_name:l}, $${Template(cypher):q}$$) AS ({cols:q})"
    return final
