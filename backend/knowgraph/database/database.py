from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from asyncer import asyncify
from psycopg import AsyncConnection, AsyncCursor, Connection, Cursor
from sqlalchemy import Engine, MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import SQLModel

from knowgraph.utils.environments import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)

from .pool import pool_manager


class DatabaseManager:
    def __init__(self, dbname: str = "postgres") -> None:
        assert isinstance(dbname, str), "Database name must be a string."
        self.dbname = dbname
        self._engine: Engine | None = None
        self._async_engine: AsyncEngine | None = None

    @contextmanager
    def session(self, schema: str = "public") -> Generator[Session]:
        engine = pool_manager.engine(self.dbname)
        with Session(engine) as session:
            try:
                if schema == "public":
                    session.execute(text("SET search_path TO 'public,bm25_catalog,tokenizer_catalog';"))
                else:
                    session.execute(text(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog;"))
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    @asynccontextmanager
    async def asession(self, schema: str = "public") -> AsyncGenerator[AsyncSession]:
        engine = await pool_manager.aengine(self.dbname)
        async with AsyncSession(engine) as session:
            try:
                await session.execute(text(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog;"))
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @contextmanager
    def connection(self, schema: str = "public") -> Generator[Connection]:
        pool = pool_manager.pool(self.dbname)
        with pool.connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog;")  # type: ignore
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @asynccontextmanager
    async def aconnection(self, schema: str = "public") -> AsyncGenerator[AsyncConnection]:
        pool = await pool_manager.apool(self.dbname)
        async with pool.connection() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog;")  # type: ignore
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    @contextmanager
    def cursor(self, schema: str = "public") -> Generator[Cursor]:
        with self.connection(schema) as conn, conn.cursor() as cursor:
            yield cursor

    @asynccontextmanager
    async def acursor(self, schema: str = "public") -> AsyncGenerator[AsyncCursor]:
        async with self.aconnection(schema) as conn, conn.cursor() as cursor:
            yield cursor

    async def acreate_table(self, table: type[SQLModel], schema: str = "public") -> None:
        await self.acreate_all()

    async def adrop_table(self, table: type[SQLModel], schema: str = "public") -> None:
        await self.adrop_all()

    async def acreate_all(self, metadata: MetaData | None = None) -> None:
        if metadata is None:
            metadata = SQLModel.metadata
        await asyncify(metadata.create_all)(pool_manager.engine(self.dbname))

    async def adrop_all(self, metadata: MetaData | None = None) -> None:
        if metadata is None:
            metadata = SQLModel.metadata

        await asyncify(metadata.drop_all)(pool_manager.engine(self.dbname))

    async def acreate_schema(self, schema: str) -> None:
        async with self.asession() as session:
            stmt = CreateSchema(schema, if_not_exists=True)
            await session.execute(stmt)
            await session.commit()

    async def adrop_schema(self, schema: str) -> None:
        async with self.asession() as session:
            stmt = DropSchema(schema, cascade=True, if_exists=True)
            await session.execute(stmt)
            await session.commit()
