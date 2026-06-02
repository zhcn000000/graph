"""
旧金山亚洲艺术博物馆爬虫
该博物馆没有公开API且有反爬保护，通过CSV文件导入数据
"""
import os
import logging
from typing import List, Dict

import pandas as pd

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)


class AsianArtMuseumScraper(BaseScraper):
    """
    旧金山亚洲艺术博物馆爬虫
    该博物馆没有公开API且有反爬保护，仅支持从CSV文件导入数据。

    使用方式：
    1. 手动收集数据或从其他来源获取
    2. 保存为 data/asianart/asianart_import.csv
    3. 运行爬取步骤即可自动导入
    """

    def __init__(self):
        super().__init__("asianart")

    def crawl(self, limit: int = 0) -> List[Dict]:
        """从CSV文件导入旧金山亚洲艺术博物馆的中国文物数据"""
        logger.info("开始处理旧金山亚洲艺术博物馆数据...")

        # 检查是否有预先准备的CSV文件
        import_csv = os.path.join(self.data_dir, "asianart_import.csv")
        if os.path.exists(import_csv):
            logger.info(f"发现预准备的数据文件: {import_csv}")
            return self._import_from_csv(import_csv, limit)

        logger.warning(
            "未找到旧金山亚洲艺术博物馆数据文件。\n"
            "该博物馆没有公开API且有反爬保护，无法自动爬取。\n"
            "请手动将数据保存为CSV文件放到: data/asianart/asianart_import.csv\n"
            "CSV格式要求: UTF-8编码，必须包含 object_id 和 title_en 字段。\n"
            "可选字段: title_zh, time_period, dynasty, type, material, "
            "description, dimensions, detail_url, image_url, "
            "credit_line, accession_number, artist, country"
        )
        return []

    def _import_from_csv(self, csv_path: str, limit: int = 0) -> List[Dict]:
        """从CSV文件导入数据"""
        logger.info(f"从CSV导入数据: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str).fillna("")

        # 确保必要字段存在
        required_fields = ["object_id", "title_en"]
        for f in required_fields:
            if f not in df.columns:
                logger.error(f"CSV缺少必要字段: {f}")
                return []

        results = []
        for _, row in df.iterrows():
            record = {}
            for field in self.get_fieldnames():
                record[field] = str(row.get(field, "")).strip() if pd.notna(row.get(field)) else ""

            if not record["object_id"] or record["object_id"] in self.processed_ids:
                continue

            # 下载图片
            if record.get("image_url"):
                img_path = self.download_image(record["image_url"], record["object_id"])
                record["image_path"] = img_path or ""
            else:
                record["image_path"] = ""

            results.append(record)
            self.processed_ids.add(record["object_id"])

            if limit > 0 and len(results) >= limit:
                break

        self._save_to_csv(results, self.get_fieldnames())
        logger.info(f"导入完成: {len(results)} 条")
        return results
