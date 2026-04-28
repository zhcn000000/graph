import ast

from sqlalchemy import Float, String, cast
from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.sql.type_api import UserDefinedType


class BM25Vector(UserDefinedType):
    cache_ok = True
    _string = String()

    def get_col_spec(self, **kw) -> str:
        return "BM25VECTOR"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                sorted_dict = dict(sorted(value.items()))
                return str(sorted_dict)
            return value

        return process

    def bind_expression(self, bindvalue):
        return cast(bindvalue, BM25Vector)

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                return ast.literal_eval(value)
            return value

        return process

    class comparator_factory(UserDefinedType.Comparator):
        def neg_bm25_rank(self, other):
            return self.op("<&>", return_type=Float)(other)


ischema_names["bm25vector"] = BM25Vector  # type: ignore
