from datetime import date
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from .database import DatabaseManager
from .tables import ArtifactRawTable


class ArtifactStore:
    def __init__(self, dbname: str | None = None) -> None:
        self.__db = DatabaseManager(dbname)

    async def ainsert_artifact(
        self,
        *,
        object_id: str = "",
        title: str = "",
        period: str = "",
        type: str = "",
        material: str = "",
        description: str = "",
        dimensions: str = "",
        museum: str,
        location: str = "",
        detail_url: str,
        image_url: str = "",
        image_data: bytes | None = None,
        credit_line: str = "",
        accession_number: str = "",
        crawl_date: date | None = None,
    ) -> UUID | None:
        async with self.__db.asession() as session:
            values: dict[str, str | date | bytes | None] = {
                "object_id": object_id,
                "title": title,
                "period": period,
                "type": type,
                "material": material,
                "description": description,
                "dimensions": dimensions,
                "museum": museum,
                "location": location,
                "detail_url": detail_url,
                "image_url": image_url,
                "image_data": image_data,
                "credit_line": credit_line,
                "accession_number": accession_number,
            }
            if crawl_date is not None:
                values["crawl_date"] = crawl_date
            stmt = (
                insert(ArtifactRawTable)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[col(ArtifactRawTable.detail_url)],
                    set_={
                        "object_id": object_id,
                        "title": title,
                        "period": period,
                        "type": type,
                        "material": material,
                        "description": description,
                        "dimensions": dimensions,
                        "museum": museum,
                        "location": location,
                        "image_url": image_url,
                        "image_data": image_data,
                        "credit_line": credit_line,
                        "accession_number": accession_number,
                    },
                )
                .returning(col(ArtifactRawTable.id))
            )
            result = await session.execute(stmt)
            await session.commit()
            row = result.fetchone()
            return row[0] if row else None

    async def ainsert_artifacts(self, artifacts: list[dict]) -> int:
        if not artifacts:
            return 0
        async with self.__db.asession() as session:
            count = 0
            for artifact in artifacts:
                values: dict[str, str | date | bytes | None] = {
                    "object_id": artifact.get("object_id", ""),
                    "title": artifact.get("title", ""),
                    "period": artifact.get("period", ""),
                    "type": artifact.get("type", ""),
                    "material": artifact.get("material", ""),
                    "description": artifact.get("description", ""),
                    "dimensions": artifact.get("dimensions", ""),
                    "museum": artifact["museum"],
                    "location": artifact.get("location", ""),
                    "detail_url": artifact["detail_url"],
                    "image_url": artifact.get("image_url", ""),
                    "image_data": artifact.get("image_data"),
                    "credit_line": artifact.get("credit_line", ""),
                    "accession_number": artifact.get("accession_number", ""),
                }
                if "crawl_date" in artifact:
                    values["crawl_date"] = artifact["crawl_date"]
                stmt = (
                    insert(ArtifactRawTable)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=[col(ArtifactRawTable.detail_url)],
                        set_={
                            "object_id": artifact.get("object_id", ""),
                            "title": artifact.get("title", ""),
                            "period": artifact.get("period", ""),
                            "type": artifact.get("type", ""),
                            "material": artifact.get("material", ""),
                            "description": artifact.get("description", ""),
                            "dimensions": artifact.get("dimensions", ""),
                            "museum": artifact["museum"],
                            "location": artifact.get("location", ""),
                            "image_url": artifact.get("image_url", ""),
                            "image_data": artifact.get("image_data"),
                            "credit_line": artifact.get("credit_line", ""),
                            "accession_number": artifact.get("accession_number", ""),
                        },
                    )
                )
                await session.execute(stmt)
                count += 1
            await session.commit()
            return count

    async def acheck_url_exists(self, detail_url: str) -> bool:
        async with self.__db.asession() as session:
            stmt = select(col(ArtifactRawTable.id)).where(col(ArtifactRawTable.detail_url) == detail_url)
            result = await session.execute(stmt)
            return result.fetchone() is not None

    async def aget_by_museum(self, museum: str) -> list[ArtifactRawTable]:
        async with self.__db.asession() as session:
            stmt = select(ArtifactRawTable).where(col(ArtifactRawTable.museum) == museum)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def aget_by_object_id(self, object_id: str, museum: str) -> ArtifactRawTable | None:
        async with self.__db.asession() as session:
            stmt = (
                select(ArtifactRawTable)
                .where(col(ArtifactRawTable.object_id) == object_id)
                .where(col(ArtifactRawTable.museum) == museum)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def aget_by_url(self, detail_url: str) -> ArtifactRawTable | None:
        async with self.__db.asession() as session:
            stmt = select(ArtifactRawTable).where(col(ArtifactRawTable.detail_url) == detail_url)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def acount_by_museum(self, museum: str) -> int:
        async with self.__db.asession() as session:
            stmt = select(func.count()).where(col(ArtifactRawTable.museum) == museum)
            result = await session.execute(stmt)
            row = result.fetchone()
            return int(row[0]) if row else 0

    async def alist_museums(self) -> list[str]:
        async with self.__db.asession() as session:
            stmt = select(col(ArtifactRawTable.museum)).distinct()
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]

    async def aget_urls_by_museum(self, museum: str) -> list[str]:
        async with self.__db.asession() as session:
            stmt = select(col(ArtifactRawTable.detail_url)).where(col(ArtifactRawTable.museum) == museum)
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]

    async def aupdate_field(self, detail_url: str, field: str, value: str) -> bool:
        async with self.__db.asession() as session:
            stmt = (
                update(ArtifactRawTable)
                .where(col(ArtifactRawTable.detail_url) == detail_url)
                .values(**{field: value})
                .returning(col(ArtifactRawTable.id))
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.fetchone() is not None

    async def adelete_by_museum(self, museum: str) -> int:
        async with self.__db.asession() as session:
            stmt = (
                delete(ArtifactRawTable)
                .where(col(ArtifactRawTable.museum) == museum)
                .returning(col(ArtifactRawTable.id))
            )
            result = await session.execute(stmt)
            await session.commit()
            return len(result.fetchall())

    async def adelete_by_url(self, detail_url: str) -> bool:
        async with self.__db.asession() as session:
            stmt = (
                delete(ArtifactRawTable)
                .where(col(ArtifactRawTable.detail_url) == detail_url)
                .returning(col(ArtifactRawTable.id))
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.fetchone() is not None
