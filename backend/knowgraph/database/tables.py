from datetime import date, datetime
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, SQLModel, col

from knowgraph.documents.embedder import EMBEDDING_DIMS

from .types import BM25Vector, Password

if TYPE_CHECKING:
    from collections.abc import Callable

    def declared_attr(fn: Callable):
        return fn


VECTOR_DIM = EMBEDDING_DIMS


class User(SQLModel, table=True):
    __tablename__ = "users"

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
    username: Annotated[
        str,
        Field(
            sa_column=Column(
                String,
                unique=True,
                nullable=False,
                index=True,
            ),
        ),
    ]
    password: Annotated[str, Field(sa_column=Column(Password, nullable=False))]

    @declared_attr
    @classmethod
    def __table_args__(cls) -> tuple:
        return (CheckConstraint(func.length(col(cls.username)) > 0, name="chk_user_name_not_empty"),)


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


class ArtifactRawTable(SQLModel, table=True):
    __tablename__ = "artifact_raw"
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
    object_id: Annotated[str, Field(sa_column=Column(String(512), nullable=True, index=True))]
    title: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    period: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    type: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    material: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    description: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    dimensions: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    museum: Annotated[str, Field(sa_column=Column(String(256), nullable=False, index=True))]
    location: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    detail_url: Annotated[str, Field(sa_column=Column(String(2048), nullable=False, unique=True))]
    image_url: Annotated[str, Field(sa_column=Column(String(2048), nullable=True))]
    image_data: Annotated[bytes | None, Field(sa_column=Column(LargeBinary, nullable=True))]
    credit_line: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    accession_number: Annotated[str, Field(sa_column=Column(String(256), nullable=True))]
    artist: Annotated[str, Field(sa_column=Column(String(512), nullable=True))]
    crawl_date: Annotated[
        date,
        Field(sa_column=Column(Date, nullable=False, server_default=func.current_date())),
    ]


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
    artifact_id: Annotated[
        UUID | None,
        Field(
            sa_column=Column(
                Uuid[UUID](native_uuid=True, as_uuid=True),
                ForeignKey(col(ArtifactRawTable.id), onupdate="CASCADE", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
        ),
    ]
    content: Annotated[str, Field(sa_column=Column(Text, nullable=True))]
    vector: Annotated[
        list[float],
        Field(sa_column=Column(Vector(VECTOR_DIM), nullable=True)),
    ]
    bmvector: Annotated[dict[int, int], Field(sa_column=Column(BM25Vector, nullable=True))]
    entities: Annotated[
        list[str],
        Field(sa_column=Column(ARRAY(String), nullable=False, server_default="{}")),
    ]
    document_index: Annotated[
        int | None,
        Field(sa_column=Column(Integer, nullable=True)),
    ]
    meta: Annotated[
        dict,
        Field(default_factory=dict, sa_column=Column("metadata", JSONB, nullable=False, server_default="{}")),
    ]
    image_url: Annotated[str | None, Field(sa_column=Column(String(2048), nullable=True))]

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
            Index("idx_documents_entities", col(cls.entities), postgresql_using="gin"),
            Index("idx_doc_index", col(cls.document_index), unique=True),
        )
