import asyncio
import logging
from datetime import date
from itertools import starmap
from uuid import UUID

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col

from .database import DatabaseManager
from .tables import ArtifactRawTable

logger = logging.getLogger(__name__)


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
        artist: str = "",
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
                "artist": artist,
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
                        "artist": artist,
                    },
                )
                .returning(col(ArtifactRawTable.id))
            )
            result = await session.execute(stmt)
            await session.commit()
            row = result.fetchone()
            return row[0] if row else None

    async def _aget_existing_urls(self, urls: list[str], session) -> set[str]:
        if not urls:
            return set()
        stmt = select(col(ArtifactRawTable.detail_url)).where(col(ArtifactRawTable.detail_url).in_(urls))
        result = await session.execute(stmt)
        return {row[0] for row in result.fetchall()}

    async def ainsert_artifacts(self, artifacts: list[dict], skip_existing: bool = False) -> list[UUID]:
        if not artifacts:
            return []
        async with self.__db.asession() as session:
            if skip_existing:
                urls = [a["detail_url"] for a in artifacts if a.get("detail_url")]
                existing = await self._aget_existing_urls(urls, session)
            else:
                existing: set[str] = set()

            ids: list[UUID] = []
            seen: set[str] = set()
            for artifact in artifacts:
                detail_url = artifact.get("detail_url", "")
                if not detail_url:
                    continue
                if skip_existing and detail_url in existing:
                    continue
                if detail_url in seen:
                    continue
                seen.add(detail_url)
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
                    "artist": artifact.get("artist", ""),
                }
                crawl_date = artifact.get("crawl_date")
                if crawl_date and isinstance(crawl_date, date):
                    values["crawl_date"] = crawl_date
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
                            "artist": artifact.get("artist", ""),
                        },
                    )
                    .returning(col(ArtifactRawTable.id))
                )
                result = await session.execute(stmt)
                row = result.fetchone()
                if row:
                    ids.append(row[0])
            await session.commit()
            return ids

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

    async def adownload_images(
        self,
        museum: str | None = None,
        limit: int = 50,
        concurrency: int = 5,
    ) -> int:
        async with self.__db.asession() as session:
            stmt = select(col(ArtifactRawTable.id), col(ArtifactRawTable.image_url)).where(
                col(ArtifactRawTable.image_url).isnot(None),
                col(ArtifactRawTable.image_url) != "",  # noqa: PLC1901
                col(ArtifactRawTable.image_data).is_(None),
            )
            if museum:
                stmt = stmt.where(col(ArtifactRawTable.museum) == museum)
            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = [(row[0], row[1]) for row in result.fetchall()]

            if not rows:
                return 0

            sem = asyncio.Semaphore(concurrency)

            async def download_one(uid: UUID, url: str) -> tuple[UUID, bytes | None]:
                async with sem:
                    try:
                        async with httpx.AsyncClient(timeout=30) as client:
                            resp = await client.get(url)
                            resp.raise_for_status()
                            return uid, resp.content
                    except Exception:
                        logger.warning("Failed to download image from %s", url)
                        return uid, None

            results = await asyncio.gather(*list(starmap(download_one, rows)))

            count = 0
            for uid, data in results:
                if data is not None:
                    ustmt = update(ArtifactRawTable).where(col(ArtifactRawTable.id) == uid).values(image_data=data)
                    await session.execute(ustmt)
                    count += 1

            await session.commit()
            return count
