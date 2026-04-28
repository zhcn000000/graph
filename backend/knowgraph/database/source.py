from typing import NotRequired, TypedDict
from uuid import UUID

from knowgraph.utils.file import FileStream
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from .database import DatabaseManager
from .tables import RAGRelation, Source


class PromptFileDict(TypedDict):
    name: str
    url: NotRequired[str]


class SourceStore:
    def __init__(self, dbname: str = "data") -> None:
        self.__db = DatabaseManager(dbname)

    async def aget_id(self, file_name: str) -> list[UUID]:
        async with self.__db.asession() as session:
            stmt = select(col(Source.id)).where(col(Source.filename) == file_name)
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]

    async def ainsert_files(self, files: list[FileStream] | FileStream) -> list[UUID]:
        if isinstance(files, FileStream):
            files = [files]
        async with self.__db.asession() as session:
            stmt = (
                insert(Source)
                .values([
                    {
                        "filename": file.name,
                        "content": file.stream.getvalue(),
                        "hash": file.file_hash,
                    }
                    for file in files
                ])
                .on_conflict_do_nothing(index_elements=[col(Source.hash)])
                .returning(col(Source.id))
            )
            result = await session.execute(stmt)
            await session.commit()
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
            stmt = select(col(RAGRelation.file_id)).where(col(RAGRelation.file_id).in_(file_ids))
            rows = (await session.execute(stmt)).all()
            referenced.update(row[0] for row in rows if row[0] is not None)
            orphan_ids = [file_id for file_id in file_ids if file_id not in referenced]
            if not orphan_ids:
                return []
            stmt = delete(Source).where(col(Source.id).in_(orphan_ids)).returning(col(Source.id))
            result = await session.execute(stmt)
            await session.commit()
            return [row[0] for row in result.fetchall()]

    async def aget_file(self, file_id: UUID) -> FileStream | None:
        async with self.__db.asession() as session:
            stmt = select(Source).where(col(Source.id) == file_id)
            result = await session.execute(stmt)
            source = result.scalar_one_or_none()
            if not source:
                return None
            content = source.content
            if not isinstance(content, bytes):
                return None
            return source.to_filestream()

    async def aget_hash_by_ids(self, file_id: list[UUID]) -> list[str]:
        if not file_id:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.hash), col(Source.id)).where(col(Source.id).in_(file_id))
            result = await session.execute(stmt)
            hash2ids = {row[1]: row[0] for row in result.fetchall()}
            if len(file_id) != len(hash2ids):
                msg = "Some file IDs not found"
                raise ValueError(msg)
            return [hash2ids.get(fid, "") for fid in file_id]

    async def aget_id_by_hashs(self, file_hashs: list[str]) -> list[UUID]:
        if not file_hashs:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.id), col(Source.hash)).where(col(Source.hash).in_(file_hashs))
            result = await session.execute(stmt)
            hash2ids = {row[1]: row[0] for row in result.fetchall()}
            if len(file_hashs) != len(hash2ids):
                msg = "Some file hashes not found"
                raise ValueError(msg)
            return [hash2ids[fhash] for fhash in file_hashs]

    async def aget_id_by_names(self, file_names: list[str]) -> list[UUID]:
        if not file_names:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.id), col(Source.filename)).where(col(Source.filename).in_(file_names))
            result = await session.execute(stmt)
            name2ids = {row[1]: row[0] for row in result.fetchall()}
            if len(file_names) != len(name2ids):
                msg = "Some file names not found"
                raise ValueError(msg)
            return [name2ids[fname] for fname in file_names]

    async def aget_name_by_ids(self, file_ids: list[UUID]) -> list[str]:
        if not file_ids:
            return []
        async with self.__db.asession() as session:
            stmt = select(col(Source.id), col(Source.filename)).where(col(Source.id).in_(file_ids))
            result = await session.execute(stmt)
            id2names = {row[0]: row[1] for row in result.fetchall()}
            if len(file_ids) != len(id2names):
                msg = "Some file IDs not found"
                raise ValueError(msg)
            return [id2names[fid] for fid in file_ids]
