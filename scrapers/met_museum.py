"""
大都会艺术博物馆爬虫
API文档：https://metmuseum.github.io/
免费公开API，无需认证
"""
import time
import logging
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

API_BASE = "https://collectionapi.metmuseum.org/public/collection/v1"


class MetMuseumScraper(BaseScraper):
    """大都会艺术博物馆爬虫"""

    def __init__(self):
        super().__init__("met")

    def _search_chinese_objects(self) -> List[int]:
        """搜索中国文物的objectID列表，使用多种搜索策略合并结果"""
        url = f"{API_BASE}/search"
        all_ids = set()

        # 多种搜索策略
        search_params = [
            {"departmentId": 6, "q": "chinese", "hasImages": "true"},
            {"departmentId": 6, "q": "china", "hasImages": "true"},
            {"departmentId": 6, "q": "dynasty", "hasImages": "true"},
        ]

        for params in search_params:
            try:
                resp = self.session.get(url, params=params, timeout=config.CRAWL_TIMEOUT)
                data = resp.json()
                ids = data.get("objectIDs", [])
                if ids:
                    all_ids.update(ids)
                    logger.info(f"搜索 {params.get('q')}: {len(ids)} 个ID")
            except Exception as e:
                logger.warning(f"搜索 {params.get('q')} 失败: {e}")

        logger.info(f"去重后共 {len(all_ids)} 个中国文物ID")
        return list(all_ids)

    def _fetch_object_detail(self, object_id: int) -> Optional[Dict]:
        """获取单个文物详情"""
        url = f"{API_BASE}/objects/{object_id}"
        try:
            resp = self.session.get(url, timeout=config.CRAWL_TIMEOUT)
            if resp.status_code != 200:
                return None
            data = resp.json()

            # 过滤：确保是来自中国的文物
            culture = (data.get("culture") or "").lower()
            country = (data.get("country") or "").lower()
            dynasty = data.get("dynasty") or ""

            is_chinese = (
                "chinese" in culture
                or "china" in country
                or "chinese" in (data.get("artistNationality") or "").lower()
            )
            if not is_chinese:
                return None

            # 提取图片URL
            image_url = data.get("primaryImage", "")
            if not image_url:
                image_url = data.get("primaryImageSmall", "")

            # 提取文物类型
            obj_type = data.get("classification") or data.get("objectName") or ""

            # 提取艺术家信息
            artist_name = (data.get("artistDisplayName") or "").strip()
            if artist_name.lower() in ("", "unknown", "anonymous"):
                artist_name = ""

            # 提取产地/国家
            country = (data.get("country") or "").strip()
            if not country and "china" in culture:
                country = "China"

            return {
                "object_id": str(object_id),
                "title_en": (data.get("title") or "").strip(),
                "title_zh": "",
                "time_period": (data.get("objectDate") or "").strip(),
                "dynasty": dynasty.strip(),
                "type": obj_type.strip(),
                "material": (data.get("medium") or "").strip(),
                "description": "",
                "dimensions": (data.get("dimensions") or "").strip(),
                "detail_url": data.get("objectURL") or "",
                "image_url": image_url,
                "credit_line": (data.get("creditLine") or "").strip(),
                "accession_number": (data.get("accessionNumber") or "").strip(),
                "artist": artist_name,
                "country": country,
            }
        except Exception as e:
            logger.debug(f"获取详情失败 {object_id}: {e}")
            return None

    def crawl(self, limit: int = 0) -> List[Dict]:
        """
        爬取大都会博物馆的中国文物
        limit: 限制爬取数量，0表示全部
        """
        logger.info("开始爬取大都会艺术博物馆...")

        # 搜索所有中国文物ID
        object_ids = self._search_chinese_objects()
        if not object_ids:
            logger.error("未搜索到任何文物ID")
            return []

        # 过滤已处理的ID
        new_ids = [oid for oid in object_ids if str(oid) not in self.processed_ids]
        logger.info(f"待爬取: {len(new_ids)} (已处理: {len(self.processed_ids)})")

        if limit > 0:
            new_ids = new_ids[:limit]

        results = []
        total = len(new_ids)
        success = 0
        fail = 0

        # 使用多线程并发获取详情
        with ThreadPoolExecutor(max_workers=config.CRAWL_WORKERS) as executor:
            future_to_id = {}
            for i, oid in enumerate(new_ids):
                future = executor.submit(self._fetch_object_detail, oid)
                future_to_id[future] = oid
                # 控制提交速度，避免API过载
                if (i + 1) % 10 == 0:
                    time.sleep(config.CRAWL_DELAY)

            for future in as_completed(future_to_id):
                oid = future_to_id[future]
                try:
                    record = future.result()
                    if record:
                        # 下载图片
                        if record.get("image_url"):
                            img_path = self.download_image(record["image_url"], record["object_id"])
                            record["image_path"] = img_path or ""
                        else:
                            record["image_path"] = ""
                        results.append(record)
                        self.processed_ids.add(str(oid))
                        success += 1
                    else:
                        fail += 1
                except Exception as e:
                    logger.debug(f"处理失败 {oid}: {e}")
                    fail += 1

                # 进度日志
                done = success + fail
                if done % 100 == 0:
                    logger.info(f"进度: {done}/{total} (成功: {success}, 失败: {fail})")

                # 每500条保存一次
                if len(results) >= 500:
                    self._save_to_csv(results, self.get_fieldnames())
                    results = []

        # 保存剩余数据
        if results:
            self._save_to_csv(results, self.get_fieldnames())

        logger.info(f"爬取完成: 成功 {success}, 失败 {fail}, 总计 {success}")
        return results
