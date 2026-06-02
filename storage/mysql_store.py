"""
MySQL数据存储模块
负责将清洗后的数据批量写入MySQL数据库
"""
import os
import logging
from datetime import datetime, date
from typing import List, Dict, Optional

import pymysql

import config

logger = logging.getLogger(__name__)


class MySQLStore:
    """MySQL数据存储"""

    def __init__(self):
        self.conn = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.conn = pymysql.connect(
                host=config.MYSQL_HOST,
                port=config.MYSQL_PORT,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                charset=config.MYSQL_CHARSET,
                autocommit=False,
            )
            logger.info(f"连接MySQL成功: {config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}")
        except Exception as e:
            logger.error(f"连接MySQL失败: {e}")
            raise

    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()

    def _execute_many(self, sql: str, data: list):
        """批量执行SQL"""
        if not data:
            return
        cursor = self.conn.cursor()
        try:
            cursor.executemany(sql, data)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"批量执行失败: {e}")
            raise
        finally:
            cursor.close()

    def insert_museums(self, museums: List[Dict]):
        """插入博物馆数据"""
        sql = """
            INSERT INTO museums (id, name, short_name, country, city, website, collection_url, created_at, updated_at)
            VALUES (%(id)s, %(name)s, %(short_name)s, %(country)s, %(city)s, %(website)s, %(collection_url)s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                name=VALUES(name), website=VALUES(website), updated_at=NOW()
        """
        self._execute_many(sql, museums)
        logger.info(f"插入博物馆: {len(museums)} 条")

    def insert_dynasties(self, dynasties: List[Dict]):
        """插入朝代数据"""
        sql = """
            INSERT INTO dynasties (id, name_zh, name_en, start_year, end_year, description, created_at)
            VALUES (%(id)s, %(name_zh)s, %(name_en)s, %(start_year)s, %(end_year)s, %(description)s, NOW())
            ON DUPLICATE KEY UPDATE
                name_zh=VALUES(name_zh), name_en=VALUES(name_en),
                start_year=VALUES(start_year), end_year=VALUES(end_year)
        """
        self._execute_many(sql, dynasties)
        logger.info(f"插入朝代: {len(dynasties)} 条")

    def insert_artists(self, artists_df):
        """插入艺术家数据"""
        if artists_df.empty:
            return

        sql = """
            INSERT INTO artists (id, name_zh, name_en, birth_year, death_year, dynasty_id, biography, baidu_url, wiki_url, created_at, updated_at)
            VALUES (%(id)s, %(name_zh)s, %(name_en)s, %(birth_year)s, %(death_year)s, %(dynasty_id)s, %(biography)s, %(baidu_url)s, %(wiki_url)s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                name_zh=VALUES(name_zh), name_en=VALUES(name_en), biography=VALUES(biography), updated_at=NOW()
        """
        records = []
        for _, row in artists_df.iterrows():
            records.append({
                "id": int(row["id"]),
                "name_zh": row.get("name_zh") or None,
                "name_en": row.get("name_en") or None,
                "birth_year": self._safe_int(row.get("birth_year")),
                "death_year": self._safe_int(row.get("death_year")),
                "dynasty_id": self._safe_int(row.get("dynasty_id")),
                "biography": row.get("biography") or None,
                "baidu_url": row.get("baidu_url") or None,
                "wiki_url": row.get("wiki_url") or None,
            })
        self._execute_many(sql, records)
        logger.info(f"插入艺术家: {len(records)} 条")

    def insert_artifacts(self, df, museum_id: int, dynasty_id_map: dict):
        """插入文物数据"""
        if df.empty:
            return 0

        sql = """
            INSERT INTO artifacts
                (object_id, title_zh, title_en, time_period, dynasty_id, type, material,
                 description, dimensions, museum_id, location_id, detail_url, image_url,
                 image_path, credit_line, accession_number, crawl_date, image_validated,
                 last_updated, created_at)
            VALUES
                (%(object_id)s, %(title_zh)s, %(title_en)s, %(time_period)s, %(dynasty_id)s,
                 %(type)s, %(material)s, %(description)s, %(dimensions)s, %(museum_id)s,
                 %(location_id)s, %(detail_url)s, %(image_url)s, %(image_path)s,
                 %(credit_line)s, %(accession_number)s, %(crawl_date)s, %(image_validated)s,
                 NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                title_zh=VALUES(title_zh), title_en=VALUES(title_en),
                time_period=VALUES(time_period), dynasty_id=VALUES(dynasty_id),
                type=VALUES(type), material=VALUES(material),
                description=VALUES(description), image_url=VALUES(image_url),
                last_updated=NOW()
        """
        records = []
        for _, row in df.iterrows():
            dynasty_name = row.get("dynasty", "")
            dynasty_id = dynasty_id_map.get(dynasty_name) if dynasty_name else None

            records.append({
                "object_id": str(row.get("object_id", "")),
                "title_zh": row.get("title_zh") or None,
                "title_en": str(row.get("title_en", "")),
                "time_period": row.get("time_period") or None,
                "dynasty_id": dynasty_id,
                "type": row.get("type") or None,
                "material": row.get("material") or None,
                "description": row.get("description") or None,
                "dimensions": row.get("dimensions") or None,
                "museum_id": museum_id,
                "location_id": None,
                "detail_url": str(row.get("detail_url", "")),
                "image_url": str(row.get("image_url", "")),
                "image_path": row.get("image_path") or None,
                "credit_line": row.get("credit_line") or None,
                "accession_number": row.get("accession_number") or None,
                "crawl_date": date.today().isoformat(),
                "image_validated": 1 if row.get("image_path") else 0,
            })

        # 分批插入，每批500条
        batch_size = 500
        total = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            self._execute_many(sql, batch)
            total += len(batch)
            logger.info(f"  插入文物: {total}/{len(records)}")

        logger.info(f"插入文物总计: {total} 条")
        return total

    def insert_artifact_images(self, df, museum_id: int):
        """插入文物图片数据"""
        if df.empty:
            return

        sql = """
            INSERT INTO artifact_images (artifact_id, image_url, image_path, is_primary, sort_order)
            VALUES (
                (SELECT id FROM artifacts WHERE object_id=%(object_id)s AND museum_id=%(museum_id)s LIMIT 1),
                %(image_url)s, %(image_path)s, %(is_primary)s, %(sort_order)s
            )
        """
        records = []
        for _, row in df.iterrows():
            img_url = row.get("image_url", "")
            if not img_url:
                continue
            records.append({
                "object_id": str(row.get("object_id", "")),
                "museum_id": museum_id,
                "image_url": str(img_url),
                "image_path": row.get("image_path") or None,
                "is_primary": 1,
                "sort_order": 1,
            })
        self._execute_many(sql, records)
        logger.info(f"插入图片记录: {len(records)} 条")

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        """安全转换为整数"""
        if val is None or str(val).strip() in ("", "nan", "None"):
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None
