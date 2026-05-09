import logging
from contextlib import suppress
from time import sleep

from age.age import AgeLoader
from asyncer import runnify, syncify
from orjson import dumps, loads
from pgvector.psycopg.bit import register_bit_info
from pgvector.psycopg.halfvec import register_halfvec_info
from pgvector.psycopg.sparsevec import register_sparsevec_info
from pgvector.psycopg.vector import register_vector_info
from psycopg import AsyncConnection, Connection
from psycopg.conninfo import make_conninfo
from psycopg.types import TypeInfo
from psycopg.types.hstore import register_hstore
from psycopg.types.json import set_json_dumps, set_json_loads
from psycopg.types.shapely import register_shapely
from psycopg_pool import AsyncConnectionPool, ConnectionPool
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from knowgraph.utils.environments import settings

from .types import BM25Dumper, BM25Loader


def register_type(context: Connection) -> None:
    info = TypeInfo.fetch(context, "vector")
    if info is not None:
        register_vector_info(context, info)
    info = TypeInfo.fetch(context, "bit")
    if info is not None:
        register_bit_info(context, info)
    info = TypeInfo.fetch(context, "halfvec")
    if info is not None:
        register_halfvec_info(context, info)
    info = TypeInfo.fetch(context, "sparsevec")
    if info is not None:
        register_sparsevec_info(context, info)
    info = TypeInfo.fetch(context, "hstore")
    if info is not None:
        register_hstore(info, context)
    info = TypeInfo.fetch(context, "geometry")
    if info is not None:
        register_shapely(info, context)
    info = TypeInfo.fetch(context, "agtype")
    if info is not None:
        context.adapters.register_loader(info.oid, AgeLoader)
        context.adapters.register_loader(info.array_oid, AgeLoader)
    info = TypeInfo.fetch(context, "bm25vector")
    if info is not None:
        context.adapters.register_loader(info.oid, BM25Loader)
        context.adapters.register_loader(info.array_oid, BM25Loader)
        context.adapters.register_dumper(dict, BM25Dumper.build(info.oid))
    set_json_loads(loads, context)
    set_json_dumps(dumps, context)


async def register_type_async(context: AsyncConnection) -> None:
    info = await TypeInfo.fetch(context, "vector")
    if info is not None:
        register_vector_info(context, info)
    info = await TypeInfo.fetch(context, "bit")
    if info is not None:
        register_bit_info(context, info)
    info = await TypeInfo.fetch(context, "halfvec")
    if info is not None:
        register_halfvec_info(context, info)
    info = await TypeInfo.fetch(context, "sparsevec")
    if info is not None:
        register_sparsevec_info(context, info)
    info = await TypeInfo.fetch(context, "hstore")
    if info is not None:
        register_hstore(info, context)
    info = await TypeInfo.fetch(context, "geometry")
    if info is not None:
        register_shapely(info, context)
    info = await TypeInfo.fetch(context, "agtype")
    if info is not None:
        context.adapters.register_loader(info.oid, AgeLoader)
        context.adapters.register_loader(info.array_oid, AgeLoader)
    info = await TypeInfo.fetch(context, "bm25vector")
    if info is not None:
        context.adapters.register_loader(info.oid, BM25Loader)
        context.adapters.register_loader(info.array_oid, BM25Loader)
        context.adapters.register_dumper(dict, BM25Dumper.build(info.oid))
    set_json_loads(loads, context)
    set_json_dumps(dumps, context)


class ConnectionPoolManager:
    _pools: dict[str, ConnectionPool] = {}
    _apools: dict[str, AsyncConnectionPool] = {}
    _engines: dict[str, Engine] = {}
    _aengines: dict[str, AsyncEngine] = {}

    def __init__(self, min_size: int = 1, max_size: int = 20, timeout: int = 5) -> None:
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.dbname = settings.POSTGRES_DB
        self.conninfo = make_conninfo(
            user=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            connect_timeout=timeout,
        )
        self.max_size = max_size
        self.min_size = min_size
        self.url = URL.create(
            drivername="postgresql+psycopg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.dbname,
        )

    def pool(self, dbname: str | None = None) -> ConnectionPool:
        if dbname is None:
            dbname = self.dbname
        conninfo = make_conninfo(dbname=dbname, conninfo=self.conninfo)
        if dbname not in self._pools:

            def configure_conn(conn: Connection) -> None:
                register_type(conn)
                conn.set_autocommit(True)

            def check_conn(conn: Connection) -> None:
                """Check if the connection is valid and clean up transaction state if needed."""
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")

            def reset_conn(conn: Connection) -> None:
                """Reset connection state, ensure no open transaction."""
                with conn.cursor() as cursor:
                    cursor.execute("SET search_path TO public,bm25_catalog,tokenizer_catalog;")

            self._pools[dbname] = ConnectionPool(
                conninfo,
                name=dbname,
                close_returns=True,
                max_idle=60.0,
                max_lifetime=10 * 60.0,
                min_size=self.min_size,
                max_size=self.max_size,
                configure=configure_conn,
                reset=reset_conn,
                check=check_conn,
                open=False,
            )
        if self._pools[dbname].closed:
            self._pools[dbname].open()
        return self._pools[dbname]

    async def apool(self, dbname: str | None = None) -> AsyncConnectionPool:
        conninfo = make_conninfo(dbname=dbname, conninfo=self.conninfo)
        if dbname is None:
            dbname = self.dbname
        if dbname not in self._apools:

            async def configure_conn(conn: AsyncConnection) -> None:
                await register_type_async(conn)
                await conn.set_autocommit(True)
                async with conn.cursor() as cursor:
                    await cursor.execute("SET work_mem='8MB';")
                    await cursor.execute("SET maintenance_work_mem='512MB';")

            async def check_conn(conn: AsyncConnection) -> None:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")

            async def reset_conn(conn: AsyncConnection) -> None:
                """Reset connection state, ensure no open transaction."""
                async with conn.cursor() as cursor:
                    await cursor.execute("SET search_path TO public,bm25_catalog,tokenizer_catalog;")

            logging.debug("Creating new connection pool for database: %s", conninfo)
            self._apools[dbname] = AsyncConnectionPool(
                conninfo,
                name=dbname,
                close_returns=True,
                max_idle=60.0,
                max_lifetime=10 * 60.0,
                min_size=self.min_size,
                max_size=self.max_size,
                configure=configure_conn,
                reset=reset_conn,
                check=check_conn,
                open=False,
            )
        if self._apools[dbname].closed:
            await self._apools[dbname].open()
        return self._apools[dbname]

    def engine(self, dbname: str | None = None) -> Engine:
        if dbname is None:
            dbname = self.dbname
        url = self.url.set(database=dbname)
        if dbname not in self._engines:
            self._engines[dbname] = create_engine(
                url=url,
                # creator=self.pool(dbname=dbname).getconn,
                # poolclass=NullPool,
            )
        return self._engines[dbname]

    async def aengine(self, dbname: str | None = None) -> AsyncEngine:
        if dbname is None:
            dbname = self.dbname
        url = self.url.set(database=dbname)
        if dbname not in self._aengines:
            self._aengines[dbname] = create_async_engine(
                url=url,
                # async_creator=(await self.apool(dbname=dbname)).getconn,
                # poolclass=NullPool,
            )
        return self._aengines[dbname]

    def close(self) -> None:
        for pool in self._pools.values():
            with suppress(Exception):
                if not pool.closed:
                    pool.close()

    async def aclose(self) -> None:
        for apool in self._apools.values():
            with suppress(Exception):
                if not apool.closed:
                    await apool.close()

    def __del__(self) -> None:
        self.close()
        try:
            syncify(self.aclose, raise_sync_error=False)()
        except Exception:
            with suppress(Exception):
                runnify(self.aclose)()
        sleep(1)


pool_manager = ConnectionPoolManager()
