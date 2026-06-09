import logging
from datetime import date

import httpx

from .base import BaseCrawlerAdapter

SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"

logger = logging.getLogger(__name__)


class MetMuseumCrawlerAdapter(BaseCrawlerAdapter):
    museum_name = "The Metropolitan Museum of Art"
    museum_location = "New York, USA"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                },
            )
        return self._client

    async def search(self) -> list[dict]:
        client = await self._ensure_client()
        keywords = ["China", "Chinese"]
        all_ids: set[int] = set()

        for keyword in keywords:
            params: dict[str, str | int] = {"q": keyword}
            while True:
                try:
                    resp = await client.get(SEARCH_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    ids = data.get("objectIDs", [])
                    all_ids.update(ids)
                    logger.info("Keyword '%s': %d results", keyword, len(ids))
                    if data.get("next"):
                        params["page"] = data["next"]
                    else:
                        break
                except Exception:
                    logger.exception("Search API failed for keyword '%s'", keyword)
                    break

        logger.info("Total deduped object IDs: %d", len(all_ids))
        results: list[dict] = []
        for obj_id in sorted(all_ids):
            if obj_id > 1:
                results.append({
                    "object_id": str(obj_id),
                    "detail_url": f"{OBJECT_URL}/{obj_id}",
                })
        return results

    async def get_detail(self, item: dict) -> dict | None:
        object_id = item.get("object_id", "")
        url = f"{OBJECT_URL}/{object_id}"
        client = await self._ensure_client()

        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("Failed to fetch object detail: %s", object_id)
            return None

        title = data.get("title") or ""
        period = data.get("objectDate") or ""
        medium = data.get("medium") or ""
        primary_image = data.get("primaryImage") or ""
        object_url = data.get("objectURL") or ""
        artist = data.get("artistDisplayName") or ""
        classification = data.get("classification") or ""
        dimensions = data.get("dimensions") or ""
        credit_line = data.get("creditLine") or ""
        accession_number = data.get("accessionNumber") or ""

        return {
            "object_id": str(object_id),
            "title": title,
            "period": period,
            "type": classification,
            "material": medium,
            "description": "",
            "dimensions": dimensions,
            "museum": self.museum_name,
            "location": "",
            "detail_url": object_url or url,
            "image_url": primary_image,
            "credit_line": credit_line,
            "accession_number": accession_number,
            "artist": artist,
            "crawl_date": date.today(),
        }

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
