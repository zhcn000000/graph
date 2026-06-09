import asyncio
import logging
import time

from knowgraph.database.artifact import ArtifactStore

from .adapters.base import BaseCrawlerAdapter
from .models import CrawlResult

logger = logging.getLogger(__name__)


class AdapterCrawler:
    def __init__(
        self,
        adapter: BaseCrawlerAdapter,
        store: ArtifactStore | None = None,
        concurrency: int = 40,
        refresh_days: int = 7,
    ) -> None:
        self._adapter = adapter
        self._store = store or ArtifactStore()
        self._concurrency = concurrency
        self._refresh_days = refresh_days

    async def acrawl(self) -> CrawlResult:
        result = CrawlResult(museum=self._adapter.museum_name)
        t0 = time.monotonic()

        if getattr(self._adapter, "use_streaming", False):
            try:
                await self._crawl_streaming(result)
            finally:
                await self._adapter.aclose()
            result.elapsed = time.monotonic() - t0
            logger.info(
                "%s: stored=%d, skipped=%d, errors=%d, elapsed=%.1fs",
                result.museum,
                result.stored,
                result.skipped,
                result.errors,
                result.elapsed,
            )
            return result

        search_results = await self._adapter.search()
        result.total_urls = len(search_results)
        logger.info(
            "%s: %d identifiers collected",
            self._adapter.museum_name,
            len(search_results),
        )

        if not search_results:
            result.elapsed = time.monotonic() - t0
            return result

        stale_items: list[dict] = []
        fresh_urls: set[str] = set()

        if self._refresh_days > 0:
            existing = await self._store.aget_urls_by_museum(self._adapter.museum_name)
            existing_set: set[str] = set(existing)

            for item in search_results:
                url = item.get("detail_url", "")
                if url in existing_set:
                    fresh_urls.add(url)
                    result.skipped += 1
                else:
                    stale_items.append(item)
        else:
            stale_items = search_results

        result.filtered_urls = len(stale_items)
        logger.info(
            "%s: %d new/stale items to fetch, %d fresh items skipped",
            self._adapter.museum_name,
            len(stale_items),
            result.skipped,
        )

        if not stale_items:
            await self._adapter.aclose()
            result.elapsed = time.monotonic() - t0
            return result

        try:
            is_sequential = getattr(self._adapter, "is_sequential", False)

            if is_sequential:
                await self._crawl_sequential(stale_items, result)
            else:
                await self._crawl_concurrent(stale_items, result)
        finally:
            await self._adapter.aclose()

        result.elapsed = time.monotonic() - t0
        logger.info(
            "%s: stored=%d, skipped=%d, errors=%d, elapsed=%.1fs",
            result.museum,
            result.stored,
            result.skipped,
            result.errors,
            result.elapsed,
        )
        return result

    async def _crawl_streaming(self, result: CrawlResult) -> None:
        existing_set: set[str] = set()
        if self._refresh_days > 0:
            existing = await self._store.aget_urls_by_museum(self._adapter.museum_name)
            existing_set = set(existing)
            logger.info("Loaded %d existing URLs for delta check", len(existing_set))

        stored = 0
        skipped = 0
        errors = 0
        total = 0

        async for data in self._adapter.astream_items():
            total += 1
            url = data.get("detail_url", "")

            if self._refresh_days > 0 and url in existing_set:
                skipped += 1
                logger.debug("Skipped (fresh): %s", url)
                if total % 50 == 0:
                    logger.info("Progress: %d total, %d stored, %d skipped", total, stored, skipped)
                continue

            try:
                await self._store.ainsert_artifact(**data)
                stored += 1
                logger.info("Stored [%d/%d]: %s", stored, total, data.get("title", "")[:60])
            except Exception:
                logger.exception("DB insert failed for %s", url)
                errors += 1
                result.error_details.append(f"DB insert failed: {url}")

            if total % 50 == 0:
                logger.info("Progress: %d total, %d stored, %d skipped, %d errors", total, stored, skipped, errors)

        result.total_urls = total
        result.stored = stored
        result.skipped = skipped
        result.errors = errors
        result.crawled_urls = stored
        logger.info("Streaming complete: %d total, %d stored, %d skipped, %d errors", total, stored, skipped, errors)

    async def _crawl_concurrent(self, items: list[dict], result: CrawlResult) -> None:
        sem = asyncio.Semaphore(self._concurrency)
        stored: int = 0
        errors: int = 0

        async def process_one(item: dict) -> None:
            nonlocal stored, errors
            async with sem:
                data = await self._adapter.get_detail(item)
                if data is None:
                    errors += 1
                    result.error_details.append(f"Failed to fetch: {item.get('detail_url', 'unknown')}")
                    return
                try:
                    await self._store.ainsert_artifact(**data)
                    stored += 1
                except Exception:
                    logger.exception("DB insert failed for %s", data.get("detail_url", ""))
                    errors += 1
                    result.error_details.append(f"DB insert failed: {data.get('detail_url', 'unknown')}")

        tasks = [process_one(item) for item in items]
        await asyncio.gather(*tasks)

        result.stored = stored
        result.errors = errors
        result.crawled_urls = stored + errors

    async def _crawl_sequential(self, items: list[dict], result: CrawlResult) -> None:
        stored = 0
        errors = 0

        for i, item in enumerate(items):
            logger.info(
                "%s: processing %d/%d: %s",
                self._adapter.museum_name,
                i + 1,
                len(items),
                item.get("detail_url", ""),
            )
            data = await self._adapter.get_detail(item)
            if data is None:
                errors += 1
                result.error_details.append(f"Failed to fetch: {item.get('detail_url', 'unknown')}")
                continue
            try:
                await self._store.ainsert_artifact(**data)
                stored += 1
                logger.info("Stored: %s", data.get("title", "")[:60])
            except Exception:
                logger.exception("DB insert failed for %s", data.get("detail_url", ""))
                errors += 1
                result.error_details.append(f"DB insert failed: {data.get('detail_url', 'unknown')}")

        result.stored = stored
        result.errors = errors
        result.crawled_urls = stored + errors
