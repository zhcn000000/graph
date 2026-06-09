import logging
from datetime import date

import httpx

from .base import BaseCrawlerAdapter

SEARCH_URL = "https://prod.philamuseumsearch.org/v1/search"
DETAIL_URL = "https://pma-collection.web.app/gen2/v1/objects"

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {500, 502, 503, 504}


class PhilaMuseumCrawlerAdapter(BaseCrawlerAdapter):
    museum_name = "Philadelphia Museum of Art"
    museum_location = "Philadelphia, Pennsylvania, USA"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._detail_client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def _get_json(self, url: str, retries: int = 3) -> dict:
        client = await self._ensure_client()
        for attempt in range(retries):
            try:
                resp = await client.get(url)
                if resp.status_code in _RETRY_STATUSES:
                    logger.warning("Retry %d/%d for %s (status %d)", attempt + 1, retries, url, resp.status_code)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception:
                if attempt < retries - 1:
                    logger.warning("Retry %d/%d for %s", attempt + 1, retries, url)
                else:
                    raise
        return {}

    async def _post_json(self, url: str, payload: dict, headers: dict, retries: int = 3) -> dict:
        client = await self._ensure_client()
        for attempt in range(retries):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in _RETRY_STATUSES:
                    logger.warning("Retry %d/%d for POST %s (status %d)", attempt + 1, retries, url, resp.status_code)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception:
                if attempt < retries - 1:
                    logger.warning("Retry %d/%d for POST %s", attempt + 1, retries, url)
                else:
                    raise
        return {}

    async def search(self) -> list[dict]:
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        }
        results: list[dict] = []
        from_offset = 0
        page_size = 48

        while True:
            page_num = (from_offset + page_size) // page_size
            logger.info("Fetching search page %d (offset %d)", page_num, from_offset)

            payload = {
                "query": "chinese",
                "paging": {"from": from_offset, "size": page_size},
            }

            try:
                data = await self._post_json(SEARCH_URL, payload, headers)
            except Exception:
                logger.exception("Search POST failed at offset %d", from_offset)
                break

            items = data.get("result", [])
            if not items:
                logger.info("No more results at offset %d", from_offset)
                break

            for item in items:
                constituents = item.get("constituents", "")
                if isinstance(constituents, str) and "Chinese" in constituents:
                    uuid = item.get("uuid", "")
                    if not uuid:
                        continue
                    image_url = item.get("imageUrl", "")
                    if image_url and not image_url.startswith("http"):
                        image_url = f"https://iiif.micr.io/{image_url}/full/full/0/default.jpg"
                    results.append({
                        "uuid": uuid,
                        "detail_url": f"https://www.philamuseum.org/collection/object/{uuid}",
                        "title": item.get("title", ""),
                        "artist": item.get("artist", ""),
                        "date": item.get("date", ""),
                        "category": item.get("category", ""),
                        "summary": item.get("summary", ""),
                        "image_url": image_url if image_url and image_url.startswith("http") else "",
                        "constituents": constituents,
                    })

            from_offset += page_size

        logger.info("Total Chinese artifacts found: %d", len(results))
        return results

    async def get_detail(self, item: dict) -> dict | None:
        uuid = item.get("uuid", "")
        url = f"{DETAIL_URL}/{uuid}"

        try:
            details = await self._get_json(url)
        except Exception:
            logger.exception("Failed to fetch detail for %s", uuid)
            return None

        dimensions = details.get("Dimensions", "")
        credit_line = details.get("CreditLine", "")
        medium = details.get("Medium", "")
        dynasty = details.get("Dynasty", "")

        time_period = item.get("date", "")
        if dynasty and time_period:
            period = f"{dynasty} ({time_period})"
        else:
            period = dynasty or time_period

        return {
            "object_id": uuid,
            "title": item.get("title", ""),
            "period": period,
            "type": item.get("category", ""),
            "material": medium,
            "description": item.get("summary", ""),
            "dimensions": dimensions,
            "museum": self.museum_name,
            "location": "",
            "detail_url": item.get("detail_url", ""),
            "image_url": item.get("image_url", ""),
            "credit_line": credit_line,
            "accession_number": "",
            "artist": item.get("artist", ""),
            "crawl_date": date.today(),
        }

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._detail_client is not None:
            await self._detail_client.aclose()
            self._detail_client = None
