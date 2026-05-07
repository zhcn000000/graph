from typing import NotRequired, TypedDict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from .database import DatabaseManager
from .tables import DocumentTable, Source


class PromptFileDict(TypedDict):
    name: str
    url: NotRequired[str]


class SourceStore:
    def __init__(self, dbname: str | None = None) -> None:
        self.__db = DatabaseManager(dbname)

    async def ainsert_source(
        self,
        name: str,
        link: str | None = None,
        artifact_id: UUID | None = None,
    ) -> UUID | None:
        async with self.__db.asession() as session:
            stmt = (
                insert(Source)
                .values(name=name, link=link, artifact_id=artifact_id)
                .on_conflict_do_nothing(index_elements=[col(Source.name)])
                .returning(col(Source.id))
            )
            result = await session.execute(stmt)
            await session.commit()
            row = result.fetchone()
            return row[0] if row else None

    async def aget_id(self, name: str) -> list[UUID]:
        async with self.__db.asession() as session:
            stmt = select(col(Source.id)).where(col(Source.name) == name)
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]

    async def adelete_files(self, file_ids: list[UUID]) -> list[UUID]:
        if not file_ids:
            return []
        async with self.__db.asession() as session:
            stmt = delete(Source).where(col(Source.id).in_(file_ids)).returning(col(Source.id))
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall()]

    async def adelete_orphan_files(self, file_ids: list[UUID]) -> list[UUID]:
        if not file_ids:
            return []
        async with self.__db.asession() as session:
            referenced: set[UUID] = set()
            stmt = select(col(DocumentTable.file_id)).where(col(DocumentTable.file_id).in_(file_ids))
            rows = (await session.execute(stmt)).all()
            referenced.update(row[0] for row in rows if row[0] is not None)
            orphan_ids = [file_id for file_id in file_ids if file_id not in referenced]
            if not orphan_ids:
                return []
            stmt = delete(Source).where(col(Source.id).in_(orphan_ids)).returning(col(Source.id))
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall()]

    async def aget_id_by_names(self, names: list[str]) -> list[UUID]:
        if not names:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.id), col(Source.name)).where(col(Source.name).in_(names))
            result = await session.execute(stmt)
            name2ids = {row[1]: row[0] for row in result.fetchall()}
            if len(names) != len(name2ids):
                msg = "Some names not found"
                raise ValueError(msg)
            return [name2ids[n] for n in names]

    async def aget_name_by_ids(self, file_ids: list[UUID]) -> list[str]:
        if not file_ids:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.id), col(Source.name)).where(col(Source.id).in_(file_ids))
            result = await session.execute(stmt)
            id2names = {row[0]: row[1] for row in result.fetchall()}
            if len(file_ids) != len(id2names):
                msg = "Some file IDs not found"
                raise ValueError(msg)
            return [id2names[fid] for fid in file_ids]

    async def aget_link_by_id(self, source_id: UUID) -> str | None:
        async with self.__db.asession() as session:
            stmt = select(col(Source.link)).where(col(Source.id) == source_id)
            result = await session.execute(stmt)
            row = result.fetchone()
            return row[0] if row else None

    async def aget_id_by_links(self, links: list[str]) -> list[UUID]:
        if not links:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.id), col(Source.link)).where(col(Source.link).in_(links))
            result = await session.execute(stmt)
            link2ids = {row[1]: row[0] for row in result.fetchall()}
            return [link2ids[lnk] for lnk in links if lnk in link2ids]
