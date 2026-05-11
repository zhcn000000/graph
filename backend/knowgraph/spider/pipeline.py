from datetime import date
from functools import cache

import httpx

from ..database.artifact import ArtifactStore


class ArtifactPipeline:
    async def process_item(self, item: dict) -> dict:
        store = self.get_store()
        if store is None:
            return item

        image_data = await self._download_image(item.get("image_url", ""))

        await store.ainsert_artifact(
            object_id=item.get("object_id", ""),
            title=item.get("title", ""),
            period=item.get("period", ""),
            type=item.get("type", ""),
            material=item.get("material", ""),
            description=item.get("description", ""),
            dimensions=item.get("dimensions", ""),
            museum=item.get("museum", ""),
            location=item.get("location", ""),
            detail_url=item.get("detail_url", ""),
            image_url=item.get("image_url", ""),
            image_data=image_data,
            credit_line=item.get("credit_line", ""),
            accession_number=item.get("accession_number", ""),
            crawl_date=item.get("crawl_date", date.today()),
        )
        return item

    @staticmethod
    async def _download_image(url: str) -> bytes | None:
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.content
        except Exception:
            pass
        return None

    @staticmethod
    @cache
    def get_store():
        return ArtifactStore()
