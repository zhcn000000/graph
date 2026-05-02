from __future__ import annotations

import sys
import time
from typing import Any

from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging

from .config import MuseumConfig
from .models import CrawlResult
from .scrapy_spider import ArtifactSitemapSpider

if "twisted.internet.reactor" not in sys.modules:
    from twisted.internet import asyncioreactor  # type: ignore[import-untyped]

    asyncioreactor.install()

_DEFAULT_SETTINGS: dict[str, Any] = {
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 1.0,
    "RANDOMIZE_DOWNLOAD_DELAY": True,
    "CONCURRENT_REQUESTS": 8,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
    "CONCURRENT_ITEMS": 100,
    "USER_AGENT": "KnowGraph Artifact Crawler/1.0 (Academic Research Project)",
    "LOG_LEVEL": "WARNING",
    "COOKIES_ENABLED": False,
    "TELNETCONSOLE_ENABLED": False,
    "RETRY_ENABLED": True,
    "RETRY_TIMES": 3,
    "DOWNLOAD_TIMEOUT": 30,
    "DEFAULT_REQUEST_HEADERS": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
    },
    "ITEM_PIPELINES": {
        "knowgraph.spider.scrapy_pipeline.ArtifactPipeline": 300,
    },
    "SPIDER_MIDDLEWARES": {},
    "DOWNLOADER_MIDDLEWARES": {},
    "EXTENSIONS": {},
}


class ScrapyCrawler:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self._settings: dict[str, Any] = {**_DEFAULT_SETTINGS}
        if settings:
            self._settings.update(settings)

    async def acrawl_museum(self, config: MuseumConfig) -> CrawlResult:
        result = CrawlResult(museum=config.name)
        t0 = time.monotonic()

        configure_logging({"LOG_LEVEL": "WARNING"})
        runner = CrawlerRunner(self._settings)
        stats_collector: dict[str, int] = {}

        await runner.crawl(
            ArtifactSitemapSpider,
            museum_config=config,
            stats_collector=stats_collector,
        )

        result.stored = stats_collector.get("stored", 0)
        result.skipped = stats_collector.get("skipped", 0)
        result.errors = stats_collector.get("errors", 0)
        result.crawled_urls = stats_collector.get("parsed", 0)
        result.elapsed = time.monotonic() - t0
        return result

    async def acrawl_museums(self, configs: list[MuseumConfig]) -> list[CrawlResult]:
        results: list[CrawlResult] = []
        for config in configs:
            result = await self.acrawl_museum(config)
            results.append(result)
        return results
