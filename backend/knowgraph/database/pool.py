from urllib.parse import quote_plus

from psycopg_pool import AsyncConnectionPool, ConnectionPool
from pydantic import SecretStr
from sqlalchemy import URL

from knowgraph.utils.environments import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)


class ConnectionPoolManager:
    _pools: dict[str, ConnectionPool] = {}
    _async_pools: dict[str, AsyncConnectionPool] = {}
    _url: URL | None = None

    @property
    def url(self) -> URL:
        if self._url is None:
            password = quote_plus(
                POSTGRES_PASSWORD.get_secret_value() if isinstance(POSTGRES_PASSWORD, SecretStr) else POSTGRES_PASSWORD
            )
            self._url = URL.create(
                drivername="postgresql",
                username=POSTGRES_USER,
                password=password,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
            )
        return self._url

    def engine(self, dbname: str = "postgres") -> ConnectionPool:
        if dbname not in self._pools:
            url = self.url.set(database=dbname)
            self._pools[dbname] = ConnectionPool(
                conninfo=str(url),
                max_size=10,
                min_size=2,
                open=True,
            )
        return self._pools[dbname]

    async def aengine(self, dbname: str = "postgres") -> AsyncConnectionPool:
        if dbname not in self._async_pools:
            url = self.url.set(database=dbname)
            self._async_pools[dbname] = AsyncConnectionPool(
                conninfo=str(url),
                max_size=10,
                min_size=2,
                open=True,
            )
        return self._async_pools[dbname]

    async def close(self) -> None:
        for pool in self._pools.values():
            pool.close()
        for pool in self._async_pools.values():
            await pool.close()
        self._pools.clear()
        self._async_pools.clear()


pool_manager = ConnectionPoolManager()
