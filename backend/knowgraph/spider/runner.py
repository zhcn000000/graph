import importlib
import logging
import time
from collections.abc import Sequence
from typing import Any

from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.log import configure_logging

from knowgraph.database.artifact import ArtifactStore
from knowgraph.spider.config import MUSEUM_CONFIGS

from .config import MuseumConfig
from .crawler import AdapterCrawler
from .models import CrawlResult
from .spider import ArtifactSitemapSpider

logger = logging.getLogger(__name__)

_DEFAULT_SETTINGS: dict[str, Any] = {
    "ROBOTSTXT_OBEY": True,
    "DOWNLOAD_DELAY": 1.0,
    "RANDOMIZE_DOWNLOAD_DELAY": True,
    "CONCURRENT_REQUESTS": 8,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
    "CONCURRENT_ITEMS": 100,
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
        "knowgraph.spider.pipeline.ArtifactPipeline": 600,
    },
    "SPIDER_MIDDLEWARES": {},
    "DOWNLOADER_MIDDLEWARES": {
        "knowgraph.spider.download.DownloadMiddleware": 600,
        "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": None,
    },
    "EXTENSIONS": {},
    "USER_AGENT": "",
}


class ScrapyCrawler:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self._settings: dict[str, Any] = {**_DEFAULT_SETTINGS}
        if settings:
            self._settings.update(settings)

    async def acrawl_museum(self, config: MuseumConfig | str) -> CrawlResult:
        if isinstance(config, str):
            config = MUSEUM_CONFIGS[config]
        if config.use_adapter_crawler:
            return await self.acrawl_adapter_museum(config)
        return await self.acrawl_sitemap_museum(config)

    async def acrawl_sitemap_museum(self, config: MuseumConfig) -> CrawlResult:
        result = CrawlResult(museum=config.name)
        t0 = time.monotonic()

        configure_logging({"LOG_LEVEL": "WARNING"})
        runner = AsyncCrawlerProcess(self._settings)
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

    async def acrawl_adapter_museum(self, config: MuseumConfig) -> CrawlResult:
        if not config.adapter_class:
            logger.error("No adapter_class configured for %s", config.key)
            return CrawlResult(museum=config.name, errors=1)

        module_path, class_name = config.adapter_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        adapter_cls = getattr(module, class_name)
        adapter = adapter_cls()
        store = ArtifactStore()

        crawler = AdapterCrawler(
            adapter=adapter,
            store=store,
            concurrency=40,
            refresh_days=config.refresh_days,
        )
        return await crawler.acrawl()

    async def acrawl_museums(self, configs: Sequence[MuseumConfig | str] | None = None) -> list[CrawlResult]:
        if configs is None:
            configs = list(MUSEUM_CONFIGS.values())
        filter_configs = []
        for config in configs:
            if isinstance(config, str):
                filter_configs.append(MUSEUM_CONFIGS[config])
            else:
                filter_configs.append(config)
        results: list[CrawlResult] = []
        for config in filter_configs:
            result = await self.acrawl_museum(config)
            results.append(result)
        return results
