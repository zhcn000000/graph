import json
import logging
from datetime import date

from scrapy import Request, Spider

from .config import MuseumConfig
from .filter import ChineseArtifactFilter

SEARCH_URL = "https://prod.philamuseumsearch.org/v1/search"
DETAIL_URL = "https://pma-collection.web.app/gen2/v1/objects"

PHILA_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)

logger = logging.getLogger(__name__)


class PhilaApiSpider(Spider):
    name = "phila_api"

    def __init__(
        self,
        museum_config: MuseumConfig | None = None,
        chinese_filter: ChineseArtifactFilter | None = None,
        stats_collector: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._museum_config = museum_config
        self._filter = chinese_filter or ChineseArtifactFilter()
        self.stats_collector: dict = stats_collector or {}
        self.stats: dict[str, int] = {"stored": 0, "skipped": 0, "errors": 0, "parsed": 0}

    def start_requests(self):
        payload = {
            "query": "chinese",
            "paging": {"from": 0, "size": 48},
        }
        yield Request(
            url=SEARCH_URL,
            method="POST",
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "User-Agent": PHILA_UA,
            },
            callback=self.parse_search,
            meta={"from_offset": 0, "page_size": 48},
        )

    def parse_search(self, response):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError, TypeError:
            logger.exception("Failed to parse search response at offset %d", response.meta.get("from_offset", 0))
            self.stats["errors"] += 1
            return

        items = data.get("result") or []
        from_offset = response.meta["from_offset"]
        page_size = response.meta["page_size"]

        for item in items:
            constituents = item.get("constituents", "")
            if not isinstance(constituents, str) or "Chinese" not in constituents:
                continue

            uuid = item.get("uuid", "")
            if not uuid:
                continue

            meta = {
                "uuid": uuid,
                "title": item.get("title", ""),
                "artist": item.get("artist", ""),
                "date": item.get("date", ""),
                "category": item.get("category", ""),
                "summary": item.get("summary", ""),
                "image_url": item.get("imageUrl", ""),
            }
            yield Request(
                url=f"{DETAIL_URL}/{uuid}",
                callback=self.parse_detail,
                meta=meta,
            )

        if items:
            next_offset = from_offset + page_size
            payload = {
                "query": "chinese",
                "paging": {"from": next_offset, "size": page_size},
            }
            yield Request(
                url=SEARCH_URL,
                method="POST",
                body=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": PHILA_UA,
                },
                callback=self.parse_search,
                meta={"from_offset": next_offset, "page_size": page_size},
            )

    def parse_detail(self, response):
        self.stats["parsed"] += 1

        try:
            details = json.loads(response.text)
        except json.JSONDecodeError, TypeError:
            logger.exception("Failed to parse detail: %s", response.url)
            self.stats["errors"] += 1
            return

        meta = response.meta

        config = self._museum_config
        museum_name = config.name if config else "Philadelphia Museum of Art"
        museum_location = config.location if config else "Philadelphia, Pennsylvania, USA"

        title = meta.get("title", "")
        medium = details.get("Medium", "")

        if not self._filter.check_content(
            title=title,
            material=medium,
            config=config,
        ):
            self.stats["skipped"] += 1
            return

        dimensions = details.get("Dimensions", "")
        credit_line = details.get("CreditLine", "")
        dynasty = details.get("Dynasty", "")
        time_period = meta.get("date", "")

        if dynasty and time_period:
            period = f"{dynasty} ({time_period})"
        else:
            period = dynasty or time_period

        uuid = meta.get("uuid", "")
        detail_url = f"https://www.philamuseum.org/collection/object/{uuid}"

        image_url = meta.get("image_url", "")
        if image_url and not image_url.startswith("http"):
            image_url = f"https://iiif.micr.io/{image_url}/full/full/0/default.jpg"
        if image_url and not image_url.startswith("http"):
            image_url = ""

        self.stats["stored"] += 1
        yield {
            "object_id": uuid,
            "title": title,
            "period": period,
            "type": meta.get("category", ""),
            "material": medium,
            "description": meta.get("summary", ""),
            "dimensions": dimensions,
            "museum": museum_name,
            "location": museum_location,
            "detail_url": detail_url,
            "image_url": image_url,
            "credit_line": credit_line,
            "accession_number": "",
            "crawl_date": date.today(),
        }

    def closed(self, reason: str) -> None:
        self.stats_collector.update(self.stats)
