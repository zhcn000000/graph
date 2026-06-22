import json
import logging
from datetime import date

from scrapy import Request, Spider

from .config import MuseumConfig
from .filter import ChineseArtifactFilter

SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"

logger = logging.getLogger(__name__)


class MetApiSpider(Spider):
    name = "met_api"

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
        for keyword in ["China", "Chinese"]:
            yield Request(
                url=f"{SEARCH_URL}?q={keyword}",
                callback=self.parse_search,
                meta={"keyword": keyword},
            )

    def parse_search(self, response):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError, TypeError:
            logger.exception("Failed to parse search response for keyword %s", response.meta.get("keyword"))
            self.stats["errors"] += 1
            return

        object_ids = data.get("objectIDs") or []
        for obj_id in object_ids:
            if isinstance(obj_id, int) and obj_id > 1:
                yield Request(
                    url=f"{OBJECT_URL}/{obj_id}",
                    callback=self.parse_detail,
                    meta={"object_id": obj_id},
                )

        next_page = data.get("next")
        if next_page:
            keyword = response.meta["keyword"]
            yield Request(
                url=f"{SEARCH_URL}?q={keyword}&page={next_page}",
                callback=self.parse_search,
                meta={"keyword": keyword},
            )

    def parse_detail(self, response):
        self.stats["parsed"] += 1

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError, TypeError:
            logger.exception("Failed to parse object detail: %s", response.url)
            self.stats["errors"] += 1
            return

        object_id = response.meta.get("object_id", 0)
        title = data.get("title") or ""
        period = data.get("objectDate") or ""
        medium = data.get("medium") or ""

        config = self._museum_config
        museum_name = config.name if config else "The Metropolitan Museum of Art"
        museum_location = config.location if config else "New York, USA"

        if not self._filter.check_content(
            title=title,
            material=medium,
            period=period,
            config=config,
        ):
            self.stats["skipped"] += 1
            return

        self.stats["stored"] += 1
        yield {
            "object_id": str(object_id),
            "title": title,
            "period": period,
            "type": data.get("classification") or "",
            "material": medium,
            "description": "",
            "dimensions": data.get("dimensions") or "",
            "museum": museum_name,
            "location": museum_location,
            "detail_url": data.get("objectURL") or response.url,
            "image_url": data.get("primaryImage") or "",
            "credit_line": data.get("creditLine") or "",
            "accession_number": data.get("accessionNumber") or "",
            "crawl_date": date.today(),
        }

    def closed(self, reason: str) -> None:
        self.stats_collector.update(self.stats)
