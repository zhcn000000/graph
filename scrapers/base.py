"""
爬虫基类
提供通用的HTTP请求、重试、图片下载等功能
"""
import os
import csv
import time
import logging
import hashlib
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """爬虫基类，所有博物馆爬虫继承此类"""

    def __init__(self, museum_key: str):
        self.museum_key = museum_key
        self.museum_config = config.MUSEUMS[museum_key]
        self.museum_id = self.museum_config["id"]
        self.data_dir = os.path.join(config.DATA_DIR, museum_key)
        self.image_dir = os.path.join(config.IMAGE_DIR, museum_key)
        self.csv_path = os.path.join(self.data_dir, f"{museum_key}_raw.csv")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)

        self.session = self._create_session()
        self.processed_ids: Set[str] = set()
        self._load_processed_ids()

    def _create_session(self) -> requests.Session:
        """创建带重试机制的HTTP session"""
        session = requests.Session()
        retries = Retry(
            total=config.CRAWL_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retries, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return session

    def _load_processed_ids(self):
        """加载已处理的文物ID，用于断点续爬"""
        if os.path.exists(self.csv_path):
            try:
                import pandas as pd
                df = pd.read_csv(self.csv_path, usecols=["object_id"], dtype=str)
                self.processed_ids = set(df["object_id"].dropna().tolist())
                logger.info(f"已加载 {len(self.processed_ids)} 个已处理ID")
            except Exception as e:
                logger.warning(f"加载已处理ID失败: {e}")

    def _save_to_csv(self, records: List[Dict], fieldnames: List[str]):
        """保存数据到CSV文件"""
        if not records:
            return
        file_exists = os.path.exists(self.csv_path) and os.path.getsize(self.csv_path) > 0
        with open(self.csv_path, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for record in records:
                row = {k: record.get(k, "") for k in fieldnames}
                writer.writerow(row)
        logger.info(f"保存 {len(records)} 条记录到 {self.csv_path}")

    def download_image(self, url: str, object_id: str) -> Optional[str]:
        """下载图片并返回本地路径"""
        if not config.IMAGE_DOWNLOAD or not url:
            return None
        try:
            # 用object_id的MD5作为文件名，避免特殊字符
            ext = ".jpg"
            filename = f"{object_id}{ext}"
            filepath = os.path.join(self.image_dir, filename)

            if os.path.exists(filepath):
                return filepath

            resp = self.session.get(url, timeout=config.CRAWL_TIMEOUT, stream=True)
            if resp.status_code == 200:
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return filepath
            else:
                logger.warning(f"图片下载失败 {url}: HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"图片下载异常 {url}: {e}")
            return None

    @abstractmethod
    def crawl(self, limit: int = 0) -> List[Dict]:
        """
        执行爬取，返回标准化字段列表。
        每条记录应包含以下字段（与init_sql.md中artifacts表对应）：
        - object_id, title_en, title_zh, time_period, dynasty,
          type, material, description, dimensions,
          detail_url, image_url, credit_line, accession_number
        """
        pass

    def get_fieldnames(self) -> List[str]:
        """返回CSV字段列表"""
        return [
            "object_id", "title_en", "title_zh", "time_period", "dynasty",
            "type", "material", "description", "dimensions",
            "detail_url", "image_url", "image_path", "credit_line", "accession_number",
            "artist", "country",
        ]
