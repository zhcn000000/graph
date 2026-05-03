from .database import DatabaseManager


async def init_db():
    DatabaseManager.create_db()
    db = DatabaseManager()
    async with db.acursor(autocommit=True) as cur:
        await cur.execute(
            """
            CREATE EXTENSION IF NOT EXISTS vchord CASCADE;
            CREATE EXTENSION IF NOT EXISTS vchord_bm25 CASCADE;
            CREATE EXTENSION IF NOT EXISTS age CASCADE;
            """
        )
        await cur.execute(
            """
            ALTER SYSTEM SET shared_preload_libraries = vchord,vchord_bm25,age;
            ALTER SYSTEM SET io_method = io_uring;
            """
        )

    await db.acreate_all()
