import os
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Annotated, Any, Self
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, SQLModel, col

from knowgraph.utils.file import FileStream

from .types import BM25Vector

if TYPE_CHECKING:
    from collections.abc import Callable

    def declared_attr(fn: Callable):
        return fn


VECTOR_DIM = 4096


class Source(SQLModel, table=True):
    __tablename__ = "source"
    id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                primary_key=True,
                server_default=func.uuidv7(),
            ),
        ),
    ]
    hash: Annotated[str, Field(sa_column=Column(String(64), nullable=False, unique=True))]
    filename: Annotated[str, Field(sa_column=Column(String, nullable=False, index=True))]
    content: Annotated[bytes, Field(sa_column=Column(LargeBinary, nullable=False))]

    def to_filestream(self) -> FileStream:
        name = os.path.split(self.filename)[-1]
        return FileStream(file_hash=str(self.hash), name=name, stream=BytesIO(self.content), file_id=self.id)

    @classmethod
    def from_filestream(cls, filestream: FileStream) -> Self:
        if filestream.file_id is not None:
            return cls(
                id=filestream.file_id,
                hash=filestream.file_hash,
                filename=filestream.name,
                content=filestream.stream.getvalue(),
            )
        return cls(
            hash=filestream.file_hash,
            filename=filestream.name,
            content=filestream.stream.getvalue(),
        )

    @declared_attr
    @classmethod
    def __table_args__(cls) -> tuple:
        return (
            CheckConstraint(func.length(col(cls.hash)) > 0, name="chk_source_hash_not_empty"),
            CheckConstraint(func.length(col(cls.filename)) > 0, name="chk_source_filename_not_empty"),
        )


class RAGTable(SQLModel, table=True):
    __tablename__ = "rag"
    id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                primary_key=True,
                server_default=func.uuidv7(),
            ),
        ),
    ]
    name: Annotated[str, Field(sa_column=Column(String, nullable=False, unique=True, index=True))]
    timestamp: Annotated[
        datetime,
        Field(sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)),
    ]
    description: Annotated[str, Field(sa_column=Column(Text, nullable=False))]

    @declared_attr
    @classmethod
    def __table_args__(cls) -> tuple:
        return (CheckConstraint(func.length(col(cls.name)) > 0, name="chk_rag_name_not_empty"),)


class RAGRelation(SQLModel, table=True):
    __tablename__ = "document_relation"
    file_id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                ForeignKey(col(Source.id), onupdate="CASCADE", ondelete="CASCADE"),
                nullable=False,
                primary_key=True,
            ),
        ),
    ]
    rag_id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                ForeignKey(col(RAGTable.id), onupdate="CASCADE", ondelete="CASCADE"),
                nullable=False,
                primary_key=True,
            ),
        ),
    ]

    @declared_attr
    @classmethod
    def __table_args__(cls) -> tuple:
        return (UniqueConstraint(col(cls.file_id), col(cls.rag_id), name="uix_rag_file_id"),)


class SessionTable(SQLModel, table=True):
    __tablename__ = "session"
    id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                primary_key=True,
                server_default=func.uuidv7(),
            ),
        ),
    ]
    name: Annotated[str, Field(sa_column=Column(String, nullable=True, index=True))]
    timestamp: Annotated[
        datetime,
        Field(sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)),
    ]


class HistoryTable(SQLModel, table=True):
    __tablename__ = "history"
    id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                primary_key=True,
                server_default=func.uuidv7(),
            ),
        ),
    ]
    session_id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid,
                ForeignKey(col(SessionTable.id), onupdate="CASCADE", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
        ),
    ]
    messages: Annotated[list[Any], Field(sa_column=Column(JSONB, nullable=False, server_default="[]"))]


class DocumentTable(SQLModel, table=True):
    __tablename__ = "documents"
    id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                primary_key=True,
                server_default=func.uuidv7(),
            ),
        ),
    ]
    file_id: Annotated[
        UUID,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                ForeignKey(col(Source.id), onupdate="CASCADE", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
        ),
    ]
    content: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    vector: Annotated[
        list[list[float]],
        Field(sa_column=Column(ARRAY(Vector(VECTOR_DIM), dimensions=1), nullable=True)),
    ]
    bmvector: Annotated[dict[int, int], Field(sa_column=Column(BM25Vector, nullable=True))]
    meta: Annotated[
        dict,
        Field(default_factory=dict, sa_column=Column("metadata", JSONB, nullable=False, server_default="{}")),
    ]

    @declared_attr
    @classmethod
    def __table_args__(cls) -> tuple:
        return (
            Index(
                "idx_documents_vector",
                col(cls.vector),
                postgresql_using="vchordrq",
                postgresql_ops={"vector": "vector_maxsim_ops"},
            ),
            Index(
                "idx_documents_bmvector",
                col(cls.bmvector),
                postgresql_using="bm25",
                postgresql_ops={"bmvector": "bm25_ops"},
            ),
        )
