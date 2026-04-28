from datetime import datetime
from typing import TypedDict
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlmodel import col

from .database import DatabaseManager
from .tables import RAGRelation, RAGTable, Source


class RAGConfigDict(TypedDict):
    id: UUID
    name: str
    description: str | None
    timestamp: datetime | None
    file_ids: list[UUID] | None


class RAGConfig:
    def __init__(self, dbname: str = "data") -> None:
        self.__db = DatabaseManager(dbname)

    async def aget(self, rag_id: UUID) -> RAGConfigDict | None:
        async with self.__db.asession() as session:
            stmt = select(RAGTable).where(col(RAGTable.id) == rag_id)
            result = (await session.execute(stmt)).scalar_one_or_none()
            files_stmt = (
                select(col(Source.id))
                .join(RAGRelation, col(Source.id) == col(RAGRelation.file_id))
                .where(col(RAGRelation.rag_id) == rag_id)
            )
            file_ids = [row[0] for row in (await session.execute(files_stmt)).fetchall()]
            if result:
                rag_config = result
                return RAGConfigDict(
                    id=rag_config.id,
                    name=rag_config.name,
                    description=rag_config.description,
                    timestamp=rag_config.timestamp,
                    file_ids=file_ids,
                )
            return None

    async def adelete(self, rag_id: UUID) -> None:
        async with self.__db.asession() as session:
            stmt = delete(RAGTable).where(col(RAGTable.id) == rag_id)
            await session.execute(stmt)

    async def alists(self) -> dict[str, RAGConfigDict]:
        async with self.__db.asession() as session:
            stmt = select(RAGTable)
            results = (await session.execute(stmt)).scalars().all()
            return {
                row.name: RAGConfigDict(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    timestamp=row.timestamp,
                    file_ids=None,
                )
                for row in results
            }

    async def ainsert(
        self,
        name: str,
        description: str | None = None,
    ) -> None:
        time = datetime.now()
        async with self.__db.asession() as session:
            stmt = insert(RAGTable).values(
                name=name,
                description=description,
                timestamp=time,
            )
            await session.execute(stmt)

    async def aupdate(
        self,
        rag_id: UUID | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        assert rag_id is not None, "rag_id must be provided for update."
        async with self.__db.asession() as session:
            value = {}
            if name is not None:
                value["name"] = name
            if description is not None:
                value["description"] = description
            stmt = update(RAGTable).where(col(RAGTable.id) == rag_id).values(**value)
            await session.execute(stmt)

    async def aget_id_by_names(self, names: list[str]) -> list[UUID]:
        async with self.__db.asession() as session:
            stmt = select(col(RAGTable.id), col(RAGTable.name)).where(
                col(RAGTable.name).in_(names),
            )
            result = await session.execute(stmt)
            name2id = {row[1]: row[0] for row in result.fetchall()}
            if len(name2id) != len(names):
                msg = "Some RAG names do not exist in the database."
                raise ValueError(msg)
            return [name2id[name] for name in names if name in name2id]

    async def aget_name_by_ids(self, ids: list[UUID]) -> list[str]:
        async with self.__db.asession() as session:
            stmt = select(col(RAGTable.id), col(RAGTable.name)).where(col(RAGTable.id).in_(ids))
            results = (await session.execute(stmt)).all()
            id2name = {row[0]: row[1] for row in results}
            if len(ids) != len(id2name):
                msg = "Some RAG IDs do not exist in the database."
                raise ValueError(msg)
            return [id2name[id_] for id_ in ids if id_ in id2name]
