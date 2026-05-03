from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete
from sqlmodel import col

from .database import DatabaseManager
from .tables import DocumentTable


class DocumentStore:
    def __init__(self, dbname: str = "data") -> None:
        self.__db = DatabaseManager(dbname)

    async def adelete_by_file_ids(self, file_ids: Sequence[UUID]) -> int:
        file_ids = list(file_ids)
        if not file_ids:
            return 0
        async with self.__db.asession() as session:
            stmt = delete(DocumentTable).where(col(DocumentTable.file_id).in_(file_ids))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0  # type: ignore

    async def adelete_orphan_by_file_ids(self, file_ids: Sequence[UUID]) -> int:
        file_ids = list(file_ids)
        if not file_ids:
            return 0
        async with self.__db.asession() as session:
            stmt = delete(DocumentTable).where(col(DocumentTable.file_id).in_(file_ids))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0  # type: ignore
