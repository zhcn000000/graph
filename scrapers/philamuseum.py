"""
费城艺术博物馆爬虫
使用其搜索API和详情API
"""
import time
import logging
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://prod.philamuseumsearch.org/v1/search"
DETAIL_URL = "https://pma-collection.web.app/gen2/v1/objects"
IMAGE_BASE = "https://iiif.micr.io"


class PhilaMuseumScraper(BaseScraper):
    """费城艺术博物馆爬虫"""

    def __init__(self):
        super().__init__("philamuseum")

    def _search_page(self, query: str, from_: int, size: int = 48) -> List[Dict]:
        """搜索一页文物"""
        payload = {
            "query": query,
            "paging": {"from": from_, "size": size},
        }
        try:
            resp = self.session.post(SEARCH_URL, json=payload, timeout=config.CRAWL_TIMEOUT)
            data = resp.json()
            results = data.get("result", [])
            # 过滤：只保留collections类型且为中国文物
            filtered = []
            for item in results:
                if item.get("type") != "collections":
                    continue
                culture = (item.get("culture") or "").lower()
                if "chinese" in culture:
                    filtered.append(item)
            return filtered
        except Exception as e:
            logger.error(f"搜索失败 (query={query}, from={from_}): {e}")
            return []

    def _fetch_detail(self, uuid: str) -> Optional[Dict]:
        """获取文物详情"""
        url = f"{DETAIL_URL}/{uuid}"
        try:
            resp = self.session.get(url, timeout=config.CRAWL_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"获取详情失败 {uuid}: {e}")
        return None

    def _build_image_url(self, short_id: str) -> str:
        """从Micrio shortId构造图片URL"""
        if not short_id:
            return ""
        return f"{IMAGE_BASE}/{short_id}/full/max/0/default.jpg"

    def _parse_item(self, item: Dict, detail: Optional[Dict] = None) -> Dict:
        """解析单条文物数据"""
        uuid = item.get("uuid", "")
        image_short_id = item.get("imageUrl", "")
        image_url = self._build_image_url(image_short_id) if image_short_id else ""

        # 优先从搜索结果取值，detail补充
        dynasty = item.get("dynasty", "")
        dimensions = ""
        credit_line = item.get("creditLine", "")
        accession_number = item.get("objectNumber", "")

        if detail:
            dynasty = detail.get("Dynasty") or dynasty
            dimensions = detail.get("Dimensions") or ""
            credit_line = detail.get("CreditLine") or credit_line
            accession_number = detail.get("ObjectNumber") or accession_number
            # 从detail获取更好的图片URL
            views = detail.get("Views", {})
            primary = views.get("PrimaryView", {})
            main_file = primary.get("MainFile", "")
            if main_file and not image_url:
                # 构造图片URL（如果有MainFile但没有micrio shortId）
                pass

        # 提取艺术家
        artist_name = (item.get("artist") or "").strip()
        if artist_name.lower() in ("artist/maker unknown", "unknown", ""):
            artist_name = ""

        # 提取产地
        country = ""
        if detail:
            geography = detail.get("Geography", [])
            if geography:
                country = geography[0].get("Country", "") or ""

        return {
            "object_id": str(uuid),
            "title_en": (item.get("title") or "").strip(),
            "title_zh": "",
            "time_period": (item.get("date") or "").strip(),
            "artist": artist_name,
            "country": country,
            "dynasty": dynasty.strip(),
            "type": (item.get("category") or "").strip(),
            "material": (item.get("medium") or "").strip(),
            "description": (item.get("summary") or "").strip(),
            "dimensions": dimensions.strip(),
            "detail_url": f"https://www.philamuseum.org/collection/object/{uuid}",
            "image_url": image_url,
            "credit_line": credit_line.strip(),
            "accession_number": accession_number.strip(),
        }

    def crawl(self, limit: int = 0) -> List[Dict]:
        """爬取费城艺术博物馆的中国文物"""
        logger.info("开始爬取费城艺术博物馆...")

        # 使用多个搜索词以覆盖更多中国文物
        queries = ["Chinese dynasty", "chinese ceramics", "chinese porcelain", "chinese painting"]
        page_size = 100
        results = []
        total_fetched = 0

        for query in queries:
            logger.info(f"搜索词: {query!r}")
            from_ = 0

            while True:
                logger.info(f"  第 {from_ // page_size + 1} 页 (from={from_})")
                items = self._search_page(query, from_, page_size)

                if not items:
                    break

                page_results = []
                for item in items:
                    uuid = item.get("uuid", "")
                    if not uuid or uuid in self.processed_ids:
                        continue

                    detail = self._fetch_detail(uuid)
                    record = self._parse_item(item, detail)

                    if record.get("image_url"):
                        img_path = self.download_image(record["image_url"], record["object_id"])
                        record["image_path"] = img_path or ""
                    else:
                        record["image_path"] = ""

                    page_results.append(record)
                    self.processed_ids.add(uuid)
                    time.sleep(config.CRAWL_DELAY)

                results.extend(page_results)
                total_fetched += len(page_results)
                logger.info(f"  本页获取: {len(page_results)}, 累计: {total_fetched}")

                if len(results) >= 200:
                    self._save_to_csv(results, self.get_fieldnames())
                    results = []

                if limit > 0 and total_fetched >= limit:
                    break

                from_ += page_size
                time.sleep(config.CRAWL_DELAY)

            if limit > 0 and total_fetched >= limit:
                break

        if results:
            self._save_to_csv(results, self.get_fieldnames())

        logger.info(f"爬取完成: 共 {total_fetched} 条")
        return results
