from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from asyncer import asyncify
from psycopg import AsyncConnection, AsyncCursor, Connection, Cursor, IsolationLevel
from sqlalchemy import Engine, MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import SQLModel

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
                    session.execute(text("SET search_path TO public,bm25_catalog,tokenizer_catalog,ag_catalog;"))
                else:
                    session.execute(
                        text(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog,ag_catalog;"),
                    )
                yield session
                if session.in_transaction():
                    session.commit()
            except Exception:
                if session.in_transaction():
                    session.rollback()
                raise

    @asynccontextmanager
    async def asession(self, schema: str = "public") -> AsyncGenerator[AsyncSession]:
        engine = await pool_manager.aengine(self.dbname)
        async with AsyncSession(engine) as session:
            try:
                await session.execute(
                    text(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog,ag_catalog;"),
                )
                yield session
                if session.in_transaction():
                    await session.commit()
            except Exception:
                if session.in_transaction():
                    await session.rollback()
                raise

    @contextmanager
    def connection(
        self,
        schema: str = "public",
        read_only: bool = False,
        autocommit: bool = True,
        deferrable: bool = False,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> Generator[Connection]:
        pool = pool_manager.pool(self.dbname)
        with pool.connection() as conn:
            conn.set_read_only(read_only)
            conn.set_isolation_level(isolation)
            conn.set_autocommit(autocommit if not read_only else False)
            conn.set_deferrable(deferrable if read_only and isolation == IsolationLevel.SERIALIZABLE else False)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog,ag_catalog;")  # type: ignore
                yield conn
                if not autocommit:
                    conn.commit()
            except Exception:
                if not autocommit:
                    conn.rollback()
                raise

    @asynccontextmanager
    async def aconnection(
        self,
        schema: str = "public",
        read_only: bool = False,
        autocommit: bool = True,
        deferrable: bool = False,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> AsyncGenerator[AsyncConnection]:
        pool = await pool_manager.apool(self.dbname)
        async with pool.connection() as conn:
            try:
                await conn.set_read_only(read_only)
                await conn.set_isolation_level(isolation)
                await conn.set_autocommit(autocommit if not read_only else False)
                await conn.set_deferrable(
                    deferrable if read_only and isolation == IsolationLevel.SERIALIZABLE else False
                )
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f"SET search_path TO '{schema}',public,bm25_catalog,tokenizer_catalog,ag_catalog;",
                    )  # type: ignore
                yield conn
                if not autocommit:
                    await conn.commit()
            except Exception:
                if not autocommit:
                    await conn.rollback()
                raise

    @contextmanager
    def cursor(
        self,
        schema: str = "public",
        read_only: bool = False,
        autocommit: bool = True,
        deferrable: bool = False,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> Generator[Cursor]:
        with self.connection(schema, read_only, autocommit, deferrable, isolation) as conn, conn.cursor() as cursor:
            yield cursor

    @asynccontextmanager
    async def acursor(
        self,
        schema: str = "public",
        read_only: bool = False,
        autocommit: bool = True,
        deferrable: bool = False,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> AsyncGenerator[AsyncCursor]:
        async with (
            self.aconnection(schema, read_only, autocommit, deferrable, isolation) as conn,
            conn.cursor() as cursor,
        ):
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
