import logging
from datetime import date

from bs4 import BeautifulSoup
from scrapy import Spider

from .config import MuseumConfig
from .filter import ChineseArtifactFilter

ROOT_URL = "https://searchcollection.asianart.org"
BASE_URL = f"{ROOT_URL}/search/china/objects/list"

logger = logging.getLogger(__name__)


class AsianArtSpider(Spider):
    name = "asian_art"

    def __init__(
        self,
        museum_config: MuseumConfig | None = None,
        chinese_filter: ChineseArtifactFilter | None = None,
        stats_collector: dict | None = None,
        start_page: int = 1,
        end_page: int = 600,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._museum_config = museum_config
        self._filter = chinese_filter or ChineseArtifactFilter()
        self.stats_collector: dict = stats_collector or {}
        self.stats: dict[str, int] = {"stored": 0, "skipped": 0, "errors": 0, "parsed": 0}
        self._start_page = start_page
        self._end_page = end_page
        self._playwright = None
        self._browser = None
        self._context = None

    def _ensure_browser(self):
        if self._playwright is not None:
            return
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

    @staticmethod
    def _check_captcha(page) -> None:
        print("\n" + "!" * 50)
        print("Please solve the CAPTCHA manually, then press Enter to continue.")
        print("!" * 50 + "\n")
        input()

    def start_requests(self):
        config = self._museum_config
        museum_name = config.name if config else "Asian Art Museum"
        museum_location = config.location if config else "San Francisco, California, USA"

        self._ensure_browser()
        assert self._context is not None
        main_page = self._context.new_page()

        main_page.goto(BASE_URL)
        self._check_captcha(main_page)

        for p_num in range(self._start_page, self._end_page + 1):
            logger.info("Processing page %d/%d", p_num, self._end_page)
            try:
                main_page.goto(f"{BASE_URL}?page={p_num}", wait_until="networkidle", timeout=60000)
                try:
                    main_page.wait_for_selector("div.text-wrap", timeout=10000)
                except Exception:
                    logger.warning("Page %d may be blocked by CAPTCHA", p_num)
                    self._check_captcha(main_page)
                    main_page.goto(f"{BASE_URL}?page={p_num}", wait_until="networkidle")

                links = main_page.eval_on_selector_all("div.text-wrap a", "elements => elements.map(e => e.href)")
                logger.info("Page %d: %d links", p_num, len(links))

                for link in links:
                    data = self._sync_get_detail(link, museum_name, museum_location)
                    if data:
                        self.stats["stored"] += 1
                        self.stats["parsed"] += 1
                        yield data

            except Exception:
                logger.exception("Failed on page %d", p_num)
                self._check_captcha(main_page)
                continue

        main_page.close()

    def _sync_get_detail(self, url: str, museum_name: str, museum_location: str) -> dict | None:
        assert self._context is not None
        page = self._context.new_page()

        while True:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_selector(".detailField", timeout=8000)
                except Exception:
                    logger.warning("Detail page may be blocked: %s", url)
                    self._check_captcha(page)
                    continue

                soup = BeautifulSoup(page.content(), "html.parser")
                item_info: dict[str, str] = {"detail_url": url}

                title_tag = soup.select_one(".detailField")
                if not title_tag:
                    page.close()
                    return None

                item_info["title"] = title_tag.get_text(strip=True)

                detail_blocks = soup.select(".detailField")
                for block in detail_blocks:
                    label = block.select_one(".detailFieldLabel")
                    value = block.select_one(".detailFieldValue")
                    if label and value:
                        key = label.get_text(strip=True).rstrip(":")
                        val = value.get_text(separator=" ", strip=True)
                        item_info[key] = val

                img_tag = soup.select_one("div.emuseum-img-wrap img")
                if img_tag:
                    src_raw = img_tag.get("src")
                    if isinstance(src_raw, str):
                        src: str = src_raw
                        img_url = ROOT_URL + src if src.startswith("/") else src
                        item_info["image_url"] = img_url

                page.close()
                return self._map_fields(item_info, museum_name, museum_location)

            except Exception:
                logger.exception("Error navigating to %s", url)
                self._check_captcha(page)
                continue

    def _map_fields(self, raw: dict[str, str], museum_name: str, museum_location: str) -> dict | None:
        title = raw.get("title", "")
        period = raw.get("Period", "")
        dynasty = raw.get("Dynasty", "")
        date_val = raw.get("Date", "")
        parts = [p for p in (period, dynasty, date_val) if p]
        combined_period = "; ".join(parts) if parts else ""

        config = self._museum_config
        if config and not self._filter.check_content(
            title=title,
            period=combined_period,
            material=raw.get("Materials", "") or raw.get("Medium", ""),
            config=config,
        ):
            self.stats["skipped"] += 1
            return None  # type: ignore[return-value]

        return {
            "object_id": raw.get("Object number", ""),
            "title": title,
            "period": combined_period,
            "type": raw.get("Classifications", ""),
            "material": raw.get("Materials", "") or raw.get("Medium", ""),
            "description": "",
            "dimensions": raw.get("Dimensions", ""),
            "museum": museum_name,
            "location": raw.get("Place of Origin", "") or raw.get("Culture", ""),
            "detail_url": raw.get("detail_url", ""),
            "image_url": raw.get("image_url", ""),
            "credit_line": raw.get("Credit Line", ""),
            "accession_number": raw.get("Object number", ""),
            "artist": raw.get("Artist", ""),
            "crawl_date": date.today(),
        }

    def parse(self, response):
        pass

    def _cleanup(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def closed(self, reason: str) -> None:
        self._cleanup()
        self.stats_collector.update(self.stats)
