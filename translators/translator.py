"""
翻译模块
支持MyMemory（免费）和百度翻译API双源翻译
"""
import os
import json
import time
import hashlib
import logging
import requests
from typing import Optional, Dict

import config

logger = logging.getLogger(__name__)


class Translator:
    """双源翻译器：MyMemory（免费）+ 百度翻译API"""

    def __init__(self):
        self.cache_path = os.path.join(config.DATA_DIR, "translate_cache.json")
        self.cache: Dict[str, str] = {}
        self._load_cache()
        self.baidu_token = None
        self.mymemory_remaining = 5000  # 估算的每日剩余字符数

    def _load_cache(self):
        """加载翻译缓存"""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"加载翻译缓存: {len(self.cache)} 条")
            except Exception as e:
                logger.warning(f"加载翻译缓存失败: {e}")

    def _save_cache(self):
        """保存翻译缓存"""
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存翻译缓存失败: {e}")

    def _cache_key(self, text: str, source: str, target: str) -> str:
        """生成缓存key"""
        return f"{source}|{target}|{text[:200]}"

    def translate_mymemory(self, text: str, source: str = "en", target: str = "zh") -> Optional[str]:
        """使用MyMemory API翻译（免费，每日5000字符）"""
        if not text or not text.strip():
            return ""

        try:
            params = {
                "q": text[:500],  # MyMemory限制500字符/次
                "langpair": f"{source}|{target}",
            }
            if config.MYMEMORY_EMAIL:
                params["de"] = config.MYMEMORY_EMAIL

            resp = requests.get(config.MYMEMORY_API_URL, params=params, timeout=10)
            data = resp.json()

            if data.get("responseStatus") == 200:
                translated = data["responseData"]["translatedText"]
                # MyMemory返回的"MYMEMORY WARNING"表示配额用完
                if "MYMEMORY WARNING" in translated:
                    logger.warning("MyMemory每日配额已用完")
                    self.mymemory_remaining = 0
                    return None
                return translated
            else:
                logger.warning(f"MyMemory翻译失败: {data.get('responseDetails')}")
                return None
        except Exception as e:
            logger.warning(f"MyMemory请求异常: {e}")
            return None

    def translate_baidu(self, text: str, source: str = "en", target: str = "zh") -> Optional[str]:
        """使用百度翻译API翻译"""
        if not text or not text.strip():
            return ""
        if not config.BAIDU_APP_ID or not config.BAIDU_SECRET_KEY:
            return None

        try:
            # 构造签名: md5(appid + q + salt + secret_key)
            salt = str(int(time.time()))
            sign_str = config.BAIDU_APP_ID + text + salt + config.BAIDU_SECRET_KEY
            sign = hashlib.md5(sign_str.encode()).hexdigest()

            params = {
                "q": text,
                "from": source,
                "to": target,
                "appid": config.BAIDU_APP_ID,
                "salt": salt,
                "sign": sign,
            }

            resp = requests.get(config.BAIDU_TRANSLATE_URL, params=params, timeout=10)
            data = resp.json()

            if "trans_result" in data:
                results = data["trans_result"]
                return "\n".join([r["dst"] for r in results])
            else:
                error_code = data.get("error_code", "unknown")
                logger.warning(f"百度翻译失败: {error_code} - {data.get('error_msg', '')}")
                return None
        except Exception as e:
            logger.warning(f"百度翻译请求异常: {e}")
            return None

    def translate(self, text: str, source: str = "en", target: str = "zh") -> str:
        """
        翻译文本，优先使用缓存，然后MyMemory，最后百度翻译
        """
        if not text or not text.strip():
            return ""

        text = text.strip()

        # 检查缓存
        ck = self._cache_key(text, source, target)
        if ck in self.cache:
            return self.cache[ck]

        # 尝试MyMemory（免费）
        result = None
        if self.mymemory_remaining > 0:
            result = self.translate_mymemory(text, source, target)
            if result:
                self.mymemory_remaining -= len(text)

        # MyMemory失败则尝试百度翻译
        if result is None:
            result = self.translate_baidu(text, source, target)

        # 都失败则返回原文
        if result is None:
            logger.warning(f"翻译失败，保留原文: {text[:50]}...")
            result = text

        # 缓存结果
        self.cache[ck] = result
        return result

    def translate_fields(self, df, fields_to_translate: list, source: str = "en", target: str = "zh"):
        """
        批量翻译DataFrame中的指定字段
        fields_to_translate: [(源字段, 目标字段), ...] 如 [("title_en", "title_zh")]
        """
        total = len(df)
        for src_field, tgt_field in fields_to_translate:
            if src_field not in df.columns:
                continue
            if tgt_field not in df.columns:
                df[tgt_field] = ""

            logger.info(f"翻译字段: {src_field} -> {tgt_field} ({total} 条)")
            translated_count = 0

            for idx, row in df.iterrows():
                src_text = str(row.get(src_field, "")).strip()
                if not src_text or src_text in ("nan", "None", ""):
                    continue

                # 如果目标字段已有值，跳过
                existing = str(row.get(tgt_field, "")).strip()
                if existing and existing not in ("nan", "None", ""):
                    continue

                translated = self.translate(src_text, source, target)
                df.at[idx, tgt_field] = translated
                translated_count += 1

                # 每翻译100条保存一次缓存
                if translated_count % 100 == 0:
                    self._save_cache()
                    logger.info(f"  翻译进度: {translated_count}/{total}")

            logger.info(f"  翻译完成: {translated_count} 条")

        # 最终保存缓存
        self._save_cache()
        return df
