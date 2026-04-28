from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from psycopg import AsyncConnection, AsyncCursor, Connection, Cursor
from psycopg_pool import AsyncConnectionPool, ConnectionPool
from knowgraph.utils.environments import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import SQLModel

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
ASYNC_DATABASE_URL = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)


class DatabaseManager:
    def __init__(self, dbname: str = "postgres") -> None:
        assert isinstance(dbname, str), "Database name must be a string."
        self.dbname = dbname
        self._engine: Engine | None = None
        self._async_engine: AsyncEngine | None = None

    def engine(self) -> Engine:
        if self._engine is None:
            url = DATABASE_URL
            self._engine = create_engine(url, poolclass=NullPool)
        return self._engine

    async def aengine(self) -> AsyncEngine:
        if self._async_engine is None:
            url = ASYNC_DATABASE_URL
            self._async_engine = create_async_engine(url, poolclass=NullPool)
        return self._async_engine

    @contextmanager
    def session(self, schema: str = "public") -> Iterator[Session]:
        engine = self.engine()
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
    async def asession(self, schema: str = "public") -> AsyncIterator[AsyncSession]:
        engine = await self.aengine()
        async with AsyncSession(engine) as session:
            try:
                await session.execute(text(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog;"))
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def pool(self) -> ConnectionPool:
        from .pool import pool_manager

        return pool_manager.engine(self.dbname)

    async def apool(self) -> AsyncConnectionPool:
        from .pool import pool_manager

        return await pool_manager.aengine(self.dbname)

    @contextmanager
    def connection(self, schema: str = "public") -> Iterator[Connection]:
        pool = self.pool()
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
    async def aconnection(self, schema: str = "public") -> AsyncIterator[AsyncConnection]:
        pool = await self.apool()
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
    def cursor(self, schema: str = "public") -> Iterator[Cursor]:
        with self.connection(schema) as conn, conn.cursor() as cursor:
            yield cursor

    @asynccontextmanager
    async def acursor(self, schema: str = "public") -> AsyncIterator[AsyncCursor]:
        async with self.aconnection(schema) as conn, conn.cursor() as cursor:
            yield cursor

    async def acreate_table(self, table: type[SQLModel], schema: str = "public") -> None:
        await self.acreate_all()

    async def adrop_table(self, table: type[SQLModel], schema: str = "public") -> None:
        await self.adrop_all()

    async def acreate_all(self, metadata: MetaData | None = None) -> None:
        if metadata is None:
            metadata = SQLModel.metadata
        from asyncer import asyncify

        await asyncify(metadata.create_all)(self.engine())

    async def adrop_all(self, metadata: MetaData | None = None) -> None:
        if metadata is None:
            metadata = SQLModel.metadata
        from asyncer import asyncify

        await asyncify(metadata.drop_all)(self.engine())

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
