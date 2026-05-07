from psycopg.sql import SQL

from .database import DatabaseManager
from .graph import AgeGraphManager


async def init_db(alter_system: bool = True) -> None:
    DatabaseManager.create_db()
    db = DatabaseManager()
    async with db.acursor(autocommit=True) as cur:
        await cur.execute(
            SQL("""
            CREATE EXTENSION IF NOT EXISTS vchord CASCADE;
            CREATE EXTENSION IF NOT EXISTS vchord_bm25 CASCADE;
            CREATE EXTENSION IF NOT EXISTS age CASCADE;
            """),
        )
    await AgeGraphManager().acreate_graph()
    await db.acreate_all()

    if alter_system:
        async with db.aconnection(autocommit=True) as conn:
            await conn.execute(
                SQL("""
                ALTER SYSTEM SET shared_preload_libraries = vchord,vchord_bm25,age;
                ALTER SYSTEM SET search_path = "$user",public,ag_catalog,bm25_catalog;
                ALTER SYSTEM SET io_method = io_uring;
                """),
            )
