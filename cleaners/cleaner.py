"""
数据清洗模块
负责朝代匹配、字段标准化、去重等
"""
import os
import re
import logging
import pandas as pd
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ─── 朝代标准数据 ─────────────────────────────────────────────
CANONICAL_DYNASTIES = [
    {"name_en": "Shang Dynasty", "name_zh": "商朝", "start_year": -1600, "end_year": -1050},
    {"name_en": "Zhou Dynasty", "name_zh": "周朝", "start_year": -1100, "end_year": -256},
    {"name_en": "Western Zhou Dynasty", "name_zh": "西周", "start_year": -1100, "end_year": -771},
    {"name_en": "Eastern Zhou Dynasty", "name_zh": "东周", "start_year": -770, "end_year": -256},
    {"name_en": "Warring States Period", "name_zh": "战国", "start_year": -476, "end_year": -221},
    {"name_en": "Qin Dynasty", "name_zh": "秦朝", "start_year": -221, "end_year": -206},
    {"name_en": "Han Dynasty", "name_zh": "汉朝", "start_year": -206, "end_year": 220},
    {"name_en": "Western Han Dynasty", "name_zh": "西汉", "start_year": -206, "end_year": 9},
    {"name_en": "Eastern Han Dynasty", "name_zh": "东汉", "start_year": 25, "end_year": 220},
    {"name_en": "Six Dynasties Period", "name_zh": "六朝", "start_year": 220, "end_year": 589},
    {"name_en": "Western Jin Dynasty", "name_zh": "西晋", "start_year": 265, "end_year": 317},
    {"name_en": "Northern and Southern Dynasties", "name_zh": "南北朝", "start_year": 317, "end_year": 589},
    {"name_en": "Northern Dynasties", "name_zh": "北朝", "start_year": 386, "end_year": 581},
    {"name_en": "Southern Dynasties", "name_zh": "南朝", "start_year": 317, "end_year": 589},
    {"name_en": "Northern Wei Dynasty", "name_zh": "北魏", "start_year": 386, "end_year": 535},
    {"name_en": "Northern Qi Dynasty", "name_zh": "北齐", "start_year": 550, "end_year": 577},
    {"name_en": "Sui Dynasty", "name_zh": "隋朝", "start_year": 581, "end_year": 618},
    {"name_en": "Tang Dynasty", "name_zh": "唐朝", "start_year": 618, "end_year": 907},
    {"name_en": "Five Dynasties", "name_zh": "五代", "start_year": 907, "end_year": 960},
    {"name_en": "Liao Dynasty", "name_zh": "辽朝", "start_year": 907, "end_year": 1125},
    {"name_en": "Song Dynasty", "name_zh": "宋朝", "start_year": 960, "end_year": 1279},
    {"name_en": "Northern Song Dynasty", "name_zh": "北宋", "start_year": 960, "end_year": 1127},
    {"name_en": "Southern Song Dynasty", "name_zh": "南宋", "start_year": 1127, "end_year": 1279},
    {"name_en": "Jin Dynasty", "name_zh": "金朝", "start_year": 1115, "end_year": 1234},
    {"name_en": "Yuan Dynasty", "name_zh": "元朝", "start_year": 1271, "end_year": 1368},
    {"name_en": "Ming Dynasty", "name_zh": "明朝", "start_year": 1368, "end_year": 1644},
    {"name_en": "Qing Dynasty", "name_zh": "清朝", "start_year": 1644, "end_year": 1911},
    {"name_en": "Republican Period", "name_zh": "中华民国", "start_year": 1912, "end_year": 1949},
]

# 匹配优先级：先匹配更具体的朝代（如"Northern Song"要优先于"Song"）
MATCH_KEYWORDS = [
    ("Qing Dynasty", "Qing"),
    ("Ming Dynasty", "Ming"),
    ("Yuan Dynasty", "Yuan"),
    ("Jin Dynasty", "Jin"),
    ("Northern Song Dynasty", "Northern Song"),
    ("Southern Song Dynasty", "Southern Song"),
    ("Song Dynasty", "Song"),
    ("Tang Dynasty", "Tang"),
    ("Sui Dynasty", "Sui"),
    ("Western Han Dynasty", "Western Han"),
    ("Eastern Han Dynasty", "Eastern Han"),
    ("Han Dynasty", "Han"),
    ("Liao Dynasty", "Liao"),
    ("Western Zhou Dynasty", "Western Zhou"),
    ("Eastern Zhou Dynasty", "Eastern Zhou"),
    ("Zhou Dynasty", "Zhou"),
    ("Shang Dynasty", "Shang"),
    ("Northern Wei Dynasty", "Northern Wei"),
    ("Northern Qi Dynasty", "Northern Qi"),
    ("Qin Dynasty", "Qin"),
    ("Warring States Period", "Warring States"),
    ("Republican Period", "Republican"),
    ("Five Dynasties", "Five Dynasties"),
    ("Six Dynasties Period", "Six Dynasties"),
    ("Northern and Southern Dynasties", "Northern and Southern"),
    ("Western Jin Dynasty", "Western Jin"),
    ("Northern Dynasties", "Northern Dynasties"),
    ("Southern Dynasties", "Southern Dynasties"),
]


def match_dynasty(raw: str) -> Optional[str]:
    """从原始朝代字符串匹配标准朝代名称"""
    if not raw or pd.isna(raw):
        return None
    raw_lower = str(raw).strip().lower()
    if not raw_lower:
        return None

    # 修正常见拼写错误
    raw_lower = raw_lower.replace("northen", "northern")
    raw_lower = raw_lower.replace("sung", "song")

    for canonical_name, keyword in MATCH_KEYWORDS:
        if keyword.lower() in raw_lower:
            return canonical_name
    return None


def get_dynasty_id_map() -> dict:
    """获取朝代名称到ID的映射"""
    return {d["name_en"]: i + 1 for i, d in enumerate(CANONICAL_DYNASTIES)}


class DataCleaner:
    """数据清洗器"""

    def __init__(self):
        self.dynasty_id_map = get_dynasty_id_map()
        self.stats = {"total": 0, "cleaned": 0, "dynasty_matched": 0, "dropped": 0}

    def clean_museum_data(self, museum_key: str) -> pd.DataFrame:
        """清洗单个博物馆的原始数据"""
        raw_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_raw.csv")
        if not os.path.exists(raw_path):
            logger.warning(f"原始数据文件不存在: {raw_path}")
            return pd.DataFrame()

        logger.info(f"清洗数据: {raw_path}")
        df = pd.read_csv(raw_path, encoding="utf-8-sig", dtype=str)
        df = df.fillna("")

        self.stats["total"] = len(df)

        # 去重（基于object_id）
        df = df.drop_duplicates(subset=["object_id"], keep="first")

        # 过滤无效记录：必须有object_id和title_en
        df = df[df["object_id"].str.strip() != ""]
        df = df[df["title_en"].str.strip() != ""]

        # 标准化朝代
        df["dynasty"] = df["dynasty"].apply(lambda x: match_dynasty(x) or "")

        # 朝代匹配统计
        dynasty_matched = (df["dynasty"] != "").sum()
        self.stats["dynasty_matched"] = dynasty_matched
        logger.info(f"朝代匹配: {dynasty_matched}/{len(df)}")

        # 清理字段值
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace("nan", "")
                df[col] = df[col].replace("None", "")
                df[col] = df[col].replace("none", "")

        # 重新编号
        df = df.reset_index(drop=True)

        self.stats["cleaned"] = len(df)
        self.stats["dropped"] = self.stats["total"] - self.stats["cleaned"]

        # 保存清洗后的数据
        clean_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_clean.csv")
        df.to_csv(clean_path, index=False, encoding="utf-8-sig")
        logger.info(f"清洗后数据保存到: {clean_path} ({len(df)} 条)")

        return df

    def clean_all(self) -> dict:
        """清洗所有博物馆数据，返回各博物馆清洗后的DataFrame"""
        all_data = {}
        for museum_key in config.MUSEUMS:
            df = self.clean_museum_data(museum_key)
            if not df.empty:
                all_data[museum_key] = df
        return all_data

    def get_dynasty_rows(self) -> list:
        """生成朝代表数据"""
        rows = []
        for i, d in enumerate(CANONICAL_DYNASTIES, start=1):
            rows.append({
                "id": i,
                "name_zh": d["name_zh"],
                "name_en": d["name_en"],
                "start_year": d["start_year"],
                "end_year": d["end_year"],
                "description": "",
            })
        return rows

    def extract_artists(self, all_data: dict) -> pd.DataFrame:
        """从所有文物数据中提取艺术家信息"""
        artists = {}
        artist_id = 1

        for museum_key, df in all_data.items():
            if "artist" in df.columns:
                for name in df["artist"].dropna().unique():
                    name = str(name).strip()
                    if not name or name.lower() in ("artist/maker unknown", "unknown", "n/a", ""):
                        continue
                    if name not in artists:
                        artists[name] = {
                            "id": artist_id,
                            "name_zh": "",
                            "name_en": name,
                            "birth_year": "",
                            "death_year": "",
                            "dynasty_id": "",
                            "biography": "",
                            "baidu_url": "",
                            "wiki_url": "",
                        }
                        artist_id += 1

        df_artists = pd.DataFrame(list(artists.values()))
        if not df_artists.empty:
            artists_path = os.path.join(config.DATA_DIR, "clean_artists.csv")
            df_artists.to_csv(artists_path, index=False, encoding="utf-8-sig")
            logger.info(f"提取艺术家: {len(df_artists)} 人")

        return df_artists
