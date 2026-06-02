"""
全局配置模块
支持环境变量覆盖，方便Docker部署
"""
import os

# ─── MySQL 配置 ───────────────────────────────────────────────
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root123")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "seitem")
MYSQL_CHARSET = "utf8mb4"

# ─── Neo4j 配置 ───────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j123")

# ─── 翻译 API 配置 ────────────────────────────────────────────
# MyMemory（免费，每日5000字符）
MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
MYMEMORY_EMAIL = os.getenv("MYMEMORY_EMAIL", "2023040219@buct.edu.cn")  # 可选，提高配额

# 百度翻译 API
BAIDU_APP_ID = os.getenv("BAIDU_APP_ID", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
BAIDU_TRANSLATE_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"

# ─── 爬虫配置 ─────────────────────────────────────────────────
CRAWL_WORKERS = int(os.getenv("CRAWL_WORKERS", "5"))
CRAWL_DELAY = float(os.getenv("CRAWL_DELAY", "0.5"))  # 请求间隔(秒)
CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", "15"))  # 请求超时(秒)
CRAWL_RETRIES = int(os.getenv("CRAWL_RETRIES", "3"))   # 重试次数

# 图片下载配置
IMAGE_DOWNLOAD = os.getenv("IMAGE_DOWNLOAD", "true").lower() == "true"
IMAGE_DIR = os.getenv("IMAGE_DIR", "images")

# ─── 数据目录 ─────────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "data")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ─── 博物馆配置 ───────────────────────────────────────────────
MUSEUMS = {
    "met": {
        "id": 1,
        "name": "Metropolitan Museum of Art",
        "short_name": "Met",
        "country": "United States",
        "city": "New York",
        "website": "https://www.metmuseum.org",
        "collection_url": "https://www.metmuseum.org/art/collection",
    },
    "asianart": {
        "id": 2,
        "name": "Asian Art Museum of San Francisco",
        "short_name": "AsianArt",
        "country": "United States",
        "city": "San Francisco",
        "website": "https://www.asianart.org",
        "collection_url": "http://searchcollection.asianart.org",
    },
    "philamuseum": {
        "id": 3,
        "name": "Philadelphia Museum of Art",
        "short_name": "Philamuseum",
        "country": "United States",
        "city": "Philadelphia",
        "website": "https://www.philamuseum.org",
        "collection_url": "https://www.philamuseum.org/collection",
    },
}
