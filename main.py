#!/usr/bin/env python3
"""
海外藏中国文物知识图谱构建系统 — 主入口
功能：数据爬取 -> 数据清洗 -> 数据翻译 -> MySQL存储 -> Neo4j存储
"""
import sys
import argparse
import logging
from datetime import datetime

import config
from scrapers import MetMuseumScraper, AsianArtMuseumScraper, PhilaMuseumScraper
from cleaners import DataCleaner
from translators import Translator
from storage import MySQLStore, Neo4jStore
from models import TripleBuilder

# ─── 日志配置 ─────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def step_crawl(limit: int = 0):
    """步骤1: 数据爬取"""
    logger.info("=" * 60)
    logger.info("步骤1: 数据爬取")
    logger.info("=" * 60)

    scrapers = [
        ("met", MetMuseumScraper),
        ("philamuseum", PhilaMuseumScraper),
        ("asianart", AsianArtMuseumScraper),
    ]

    for key, scraper_cls in scrapers:
        logger.info(f"\n--- 爬取 {config.MUSEUMS[key]['name']} ---")
        try:
            scraper = scraper_cls()
            scraper.crawl(limit=limit)
        except Exception as e:
            logger.error(f"爬取 {key} 失败: {e}", exc_info=True)


def step_clean():
    """步骤2: 数据清洗"""
    logger.info("=" * 60)
    logger.info("步骤2: 数据清洗")
    logger.info("=" * 60)

    cleaner = DataCleaner()
    all_data = cleaner.clean_all()

    # 保存朝代数据
    dynasty_rows = cleaner.get_dynasty_rows()
    import pandas as pd
    import os
    df_dynasties = pd.DataFrame(dynasty_rows)
    dynasty_path = os.path.join(config.DATA_DIR, "clean_dynasties.csv")
    df_dynasties.to_csv(dynasty_path, index=False, encoding="utf-8-sig")
    logger.info(f"朝代数据: {len(dynasty_rows)} 条 -> {dynasty_path}")

    # 提取艺术家
    cleaner.extract_artists(all_data)

    # 统计
    total = sum(len(df) for df in all_data.values())
    logger.info(f"\n清洗完成: 共 {total} 条有效文物数据")
    for key, df in all_data.items():
        logger.info(f"  {key}: {len(df)} 条")


def step_translate():
    """步骤3: 数据翻译"""
    logger.info("=" * 60)
    logger.info("步骤3: 数据翻译")
    logger.info("=" * 60)

    import pandas as pd
    import os

    translator = Translator()

    for museum_key in config.MUSEUMS:
        clean_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_clean.csv")
        if not os.path.exists(clean_path):
            logger.info(f"跳过 {museum_key}: 无清洗数据")
            continue

        logger.info(f"\n翻译 {museum_key}...")
        df = pd.read_csv(clean_path, encoding="utf-8-sig", dtype=str).fillna("")

        # 翻译字段
        df = translator.translate_fields(
            df,
            fields_to_translate=[
                ("title_en", "title_zh"),
            ],
        )

        # 保存翻译后的数据
        translated_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_translated.csv")
        df.to_csv(translated_path, index=False, encoding="utf-8-sig")
        logger.info(f"翻译后数据保存: {translated_path}")

    logger.info("\n翻译完成")


def step_store_mysql():
    """步骤4: MySQL存储"""
    logger.info("=" * 60)
    logger.info("步骤4: MySQL存储")
    logger.info("=" * 60)

    import pandas as pd
    import os
    from cleaners import DataCleaner

    store = MySQLStore()
    store.connect()

    try:
        cleaner = DataCleaner()
        dynasty_id_map = cleaner.dynasty_id_map

        # 1. 插入博物馆
        museums = []
        for key, mcfg in config.MUSEUMS.items():
            museums.append({
                "id": mcfg["id"],
                "name": mcfg["name"],
                "short_name": mcfg["short_name"],
                "country": mcfg["country"],
                "city": mcfg["city"],
                "website": mcfg["website"],
                "collection_url": mcfg["collection_url"],
            })
        store.insert_museums(museums)

        # 2. 插入朝代
        store.insert_dynasties(cleaner.get_dynasty_rows())

        # 3. 插入艺术家
        artists_path = os.path.join(config.DATA_DIR, "clean_artists.csv")
        if os.path.exists(artists_path):
            df_artists = pd.read_csv(artists_path, encoding="utf-8-sig", dtype=str).fillna("")
            store.insert_artists(df_artists)

        # 4. 插入文物
        for museum_key, mcfg in config.MUSEUMS.items():
            # 优先使用翻译后的数据
            translated_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_translated.csv")
            clean_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_clean.csv")

            data_path = translated_path if os.path.exists(translated_path) else clean_path
            if not os.path.exists(data_path):
                logger.info(f"跳过 {museum_key}: 无数据文件")
                continue

            df = pd.read_csv(data_path, encoding="utf-8-sig", dtype=str).fillna("")
            logger.info(f"\n存储 {museum_key} ({len(df)} 条)...")
            store.insert_artifacts(df, mcfg["id"], dynasty_id_map)
            store.insert_artifact_images(df, mcfg["id"])

    finally:
        store.close()

    logger.info("\nMySQL存储完成")


def step_store_neo4j():
    """步骤5: Neo4j知识图谱存储"""
    logger.info("=" * 60)
    logger.info("步骤5: Neo4j知识图谱存储")
    logger.info("=" * 60)

    import pandas as pd
    import os
    from cleaners import DataCleaner

    store = Neo4jStore()
    store.connect()

    try:
        cleaner = DataCleaner()
        dynasty_data = cleaner.get_dynasty_rows()

        # 创建约束
        store.create_constraints()

        # 创建朝代时间线
        store.create_dynasty_timeline(dynasty_data)

        # 导入各博物馆数据
        for museum_key, mcfg in config.MUSEUMS.items():
            translated_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_translated.csv")
            clean_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_clean.csv")
            raw_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_raw.csv")

            data_path = translated_path if os.path.exists(translated_path) else clean_path
            if not os.path.exists(data_path):
                data_path = raw_path
            if not os.path.exists(data_path):
                logger.info(f"跳过 {museum_key}: 无数据文件")
                continue

            df = pd.read_csv(data_path, encoding="utf-8-sig", dtype=str).fillna("")
            logger.info(f"\n导入Neo4j: {museum_key} ({len(df)} 条)...")
            store.import_artifacts(df, mcfg["name"], {}, dynasty_data)
            store.link_artifacts_artists(df)

        # 导入艺术家
        artists_path = os.path.join(config.DATA_DIR, "clean_artists.csv")
        if os.path.exists(artists_path):
            df_artists = pd.read_csv(artists_path, encoding="utf-8-sig", dtype=str).fillna("")
            store.import_artists(df_artists)

        # 统计
        stats = store.get_stats()
        logger.info(f"\nNeo4j统计: {stats}")

    finally:
        store.close()

    logger.info("\nNeo4j存储完成")


def step_triples():
    """步骤6: 三元组建模"""
    logger.info("=" * 60)
    logger.info("步骤6: 三元组建模")
    logger.info("=" * 60)

    import pandas as pd
    import os
    from cleaners import DataCleaner

    cleaner = DataCleaner()
    dynasty_data = cleaner.get_dynasty_rows()

    all_data = {}
    for museum_key in config.MUSEUMS:
        translated_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_translated.csv")
        clean_path = os.path.join(config.DATA_DIR, museum_key, f"{museum_key}_clean.csv")
        data_path = translated_path if os.path.exists(translated_path) else clean_path
        if os.path.exists(data_path):
            df = pd.read_csv(data_path, encoding="utf-8-sig", dtype=str).fillna("")
            all_data[museum_key] = df

    builder = TripleBuilder()
    builder.build_from_dataframes(all_data, dynasty_data, config.MUSEUMS)
    builder.save_to_csv()
    builder.save_as_rdf()

    logger.info("三元组建模完成")


def step_all(limit: int = 0):
    """执行全部步骤"""
    logger.info("开始全流程处理...")
    start_time = datetime.now()

    step_crawl(limit)
    step_clean()
    step_translate()
    step_store_mysql()
    step_store_neo4j()
    step_triples()

    elapsed = datetime.now() - start_time
    logger.info(f"\n全流程完成! 耗时: {elapsed}")


def main():
    parser = argparse.ArgumentParser(
        description="海外藏中国文物知识图谱构建系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py --step all              # 执行全部流程
  python main.py --step crawl --limit 100  # 爬取(限制100条)
  python main.py --step clean            # 仅清洗
  python main.py --step translate        # 仅翻译
  python main.py --step mysql            # 仅存MySQL
  python main.py --step neo4j            # 仅存Neo4j
  python main.py --step triples          # 仅生成三元组
        """,
    )
    parser.add_argument(
        "--step",
        choices=["all", "crawl", "clean", "translate", "mysql", "neo4j", "triples"],
        default="all",
        help="执行的步骤 (默认: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="每个博物馆爬取数量限制 (0=全部)",
    )

    args = parser.parse_args()

    step_map = {
        "all": lambda: step_all(args.limit),
        "crawl": lambda: step_crawl(args.limit),
        "clean": step_clean,
        "translate": step_translate,
        "mysql": step_store_mysql,
        "neo4j": step_store_neo4j,
        "triples": step_triples,
    }

    step_map[args.step]()


if __name__ == "__main__":
    main()
