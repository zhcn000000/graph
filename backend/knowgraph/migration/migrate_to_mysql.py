from datetime import datetime
from typing import Any

from knowgraph.migration.graph_reader import AGEGraphReader
from knowgraph.migration.mysql_store import MySQLStore


def safe_str(value: Any, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


def truncate(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    return value[:max_len] if len(value) > max_len else value


# 非艺术家过滤词
_SKIP_ARTIST_WORDS = {
    "unknown", "anonymous", "various", "n/a",
    "artist/maker unknown", "artist", "maker unknown",
    "unknown artist", "unknown maker",
}


def parse_artists(artist_text: str | None) -> list[str]:
    """拆分 artist 字段，过滤无效值。"""
    if not artist_text or not artist_text.strip():
        return []
    text = artist_text.strip()
    for sep in ["; ", ";", ", ", ",", "/ ", "/"]:
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            return [p for p in parts if len(p) > 1 and p.lower() not in _SKIP_ARTIST_WORDS]
    if text.lower() not in _SKIP_ARTIST_WORDS:
        return [text]
    return []


class GraphToMySQLMigrator:
    """图数据库 → MySQL 迁移编排器。"""

    def __init__(self, dry_run: bool = False, limit: int = 0, clean: bool = False):
        self.dry_run = dry_run
        self.limit = limit
        self.clean = clean
        self.reader: AGEGraphReader | None = None
        self.mysql: MySQLStore | None = None
        self._artist_map: dict[str, int] = {}
        self._pg_artist_map: dict[int, list[str]] = {}

    def run(self) -> int:
        start = datetime.now()
        self._print_header()

        self.reader = AGEGraphReader()
        self.reader.connect()
        print(f"[PG] 连接成功, {self.reader.count_nodes()} 个节点, {self.reader.count_rels()} 条关系")

        if not self.dry_run:
            self.mysql = MySQLStore()
            self.mysql.connect()
            print(f"[MySQL] 连接成功: {self.mysql.conn.host}:{self.mysql.conn.port}")

        try:
            if self.clean and not self.dry_run:
                self.mysql.truncate_all()
                print("  已清空 MySQL 所有表数据")

            self._migrate_museums()
            self._migrate_dynasties()
            self._migrate_artifacts()
            self._migrate_artists()
            self._migrate_artifact_images()
            self._migrate_artifact_artist()
        except Exception:
            import traceback
            traceback.print_exc()
            return 1
        finally:
            self.reader.close()
            if self.mysql:
                self.mysql.close()

        print(f"\n迁移完成, 总耗时: {(datetime.now() - start).total_seconds():.1f} 秒")
        if not self.dry_run:
            self._print_connection_info()
        return 0

    # ---- 内部步骤 ----

    def _print_header(self):
        print("=" * 60)
        print("图数据库 (Apache AGE) → MySQL 数据迁移")
        print("=" * 60)
        print(f"  试运行: {'是' if self.dry_run else '否'}")
        print(f"  限制:   {self.limit} 条")
        print(f"  清空:   {'是' if self.clean else '否'}")
        print()

    def _print_connection_info(self):
        from knowgraph.utils.environments import settings as s
        print(f"\nMySQL 连接信息:")
        print(f"  Host: {s.MYSQL_HOST}:{s.MYSQL_PORT}")
        print(f"  Database: {s.MYSQL_DATABASE}")
        print(f"  User: {s.MYSQL_USER}")

    def _migrate_museums(self):
        print("\n[1/6] 迁移 museums...")
        museums = self.reader.get_all_museums()
        print(f"  从图数据库获取到 {len(museums)} 个博物馆")
        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(museums)} 条")
            return

        existing = {r["name"] for r in self.mysql.query_all("SELECT name FROM museums")}
        inserted = 0
        for m in museums:
            name = m["name"].strip()
            if name in existing:
                continue
            self.mysql.insert("museums", {
                "name": name, "short_name": None, "country": "Unknown",
                "city": None, "website": None, "collection_url": None,
                "created_at": datetime.now(), "updated_at": datetime.now(),
                "latitude": None, "longitude": None,
            })
            existing.add(name)
            inserted += 1
        print(f"  已插入 {inserted} 条")

    def _migrate_dynasties(self):
        print("\n[2/6] 迁移 dynasties...")
        dynasties = self.reader.get_all_dynasties()
        seen: set[str] = set()
        unique: list[dict] = []
        for d in dynasties:
            name = d["name"].strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                unique.append({"name": name, "description": d.get("description")})
        print(f"  去重后 {len(unique)} 个朝代")
        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(unique)} 条")
            return

        existing = {r["name_en"]: r["id"] for r in self.mysql.query_all("SELECT id, name_en FROM dynasties")}
        inserted = 0
        for d in unique:
            name_en = d["name"][:100]
            if name_en in existing:
                continue
            self.mysql.insert("dynasties", {
                "name_zh": truncate(name_en, 50), "name_en": name_en,
                "start_year": None, "end_year": None,
                "description": safe_str(d.get("description")),
                "created_at": datetime.now(),
            })
            existing[name_en] = 0
            inserted += 1
        print(f"  已插入 {inserted} 条")

    def _migrate_artifacts(self):
        print(f"\n[3/6] 迁移 artifacts... (限制 {self.limit} 条)")
        graph_artifacts = self.reader.get_artifacts_with_relations(limit=self.limit)
        titles = [a["name"] for a in graph_artifacts]
        pg_details = self.reader.get_artifact_details_by_titles(titles)
        print(f"  图节点: {len(graph_artifacts)}, artifact_raw 匹配: {len(pg_details)}")

        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(graph_artifacts)} 条")
            return

        inserted = 0
        for a in graph_artifacts:
            artifact_name = a["name"]
            pg = pg_details.get(artifact_name, {})

            museum_name = a["museums"][0] if a["museums"] else (pg.get("museum") or "").strip()
            museum_id = self.mysql.get_museum_id(museum_name) if museum_name else None
            if museum_id is None:
                museum_id = self.mysql.get_first_museum_id()

            dynasty_name = a["dynasties"][0] if a["dynasties"] else None
            dynasty_id = self.mysql.get_dynasty_id(dynasty_name) if dynasty_name else None

            artifact_type = a["artifact_types"][0] if a["artifact_types"] else safe_str(pg.get("type"))
            materials = a.get("materials", [])
            material_str = "; ".join(materials) if materials else safe_str(pg.get("material"))

            data = {
                "object_id": truncate(safe_str(pg.get("object_id")) or "", 100),
                "title_zh": None,
                "title_en": truncate(artifact_name, 500),
                "time_period": truncate(safe_str(pg.get("period")), 200),
                "dynasty_id": dynasty_id,
                "type": truncate(artifact_type, 100),
                "material": truncate(material_str, 200),
                "description": safe_str(pg.get("description")),
                "dimensions": truncate(safe_str(pg.get("dimensions")), 200),
                "museum_id": museum_id,
                "location_id": None,
                "detail_url": truncate(safe_str(pg.get("detail_url")), 500),
                "image_url": truncate(safe_str(pg.get("image_url")), 500),
                "image_path": None,
                "credit_line": truncate(safe_str(pg.get("credit_line")), 300),
                "accession_number": truncate(safe_str(pg.get("accession_number")), 100),
                "crawl_date": pg.get("crawl_date"),
                "image_validated": None,
                "last_updated": datetime.now(),
                "created_at": datetime.now(),
                "provenance": None,
                "current_status": None,
            }
            last_id = self.mysql.insert("artifacts", data)
            if last_id:
                inserted += 1
                artist_names = parse_artists(safe_str(pg.get("artist")))
                if artist_names:
                    self._pg_artist_map[last_id] = artist_names
        print(f"  已插入 {inserted} 条")

    def _migrate_artists(self):
        print("\n[4/6] 迁移 artists...")
        if not self._pg_artist_map:
            print("  无艺术家数据，跳过")
            return

        all_names: set[str] = set()
        for names in self._pg_artist_map.values():
            all_names.update(names)
        print(f"  从 artifact_raw.artist 提取到 {len(all_names)} 个独立艺术家")
        if self.dry_run:
            print(f"  [DRY RUN] 将插入 {len(all_names)} 条")
            return

        existing = {r["name_en"]: r["id"] for r in self.mysql.query_all("SELECT id, name_en FROM artists")}
        inserted = 0
        for name in sorted(all_names):
            if name in existing:
                self._artist_map[name] = existing[name]
                continue
            last_id = self.mysql.insert("artists", {
                "name_zh": None, "name_en": truncate(name, 200),
                "birth_year": None, "death_year": None, "dynasty_id": None,
                "biography": None, "baidu_url": None, "wiki_url": None,
                "created_at": datetime.now(), "updated_at": datetime.now(),
            })
            if last_id:
                self._artist_map[name] = last_id
                inserted += 1
        print(f"  已插入 {inserted} 条 (共 {len(self._artist_map)} 个)")

    def _migrate_artifact_images(self):
        print("\n[5/6] 迁移 artifact_images...")
        if self.dry_run:
            print("  [DRY RUN] 跳过")
            return
        rows = self.mysql.query_all(
            "SELECT id, image_url FROM artifacts WHERE image_url IS NOT NULL AND image_url != ''"
        )
        inserted = 0
        for row in rows:
            self.mysql.insert("artifact_images", {
                "artifact_id": row["id"], "image_url": row["image_url"],
                "image_path": None, "is_primary": 1, "sort_order": 1,
            })
            inserted += 1
        print(f"  已插入 {inserted} 条")

    def _migrate_artifact_artist(self):
        print("\n[6/6] 迁移 artifact_artist...")
        if not self._pg_artist_map:
            print("  无文物-艺术家关联，跳过")
            return
        print(f"  共 {len(self._pg_artist_map)} 个文物有艺术家信息")
        if self.dry_run:
            total = sum(len(names) for names in self._pg_artist_map.values())
            print(f"  [DRY RUN] 将插入 {total} 条")
            return

        inserted = skipped = 0
        for artifact_id, names in self._pg_artist_map.items():
            for name in names:
                artist_id = self._artist_map.get(name)
                if artist_id is None:
                    skipped += 1
                    continue
                self.mysql.insert("artifact_artist", {
                    "artifact_id": artifact_id, "artist_id": artist_id,
                    "relationship_type": "created_by",
                })
                inserted += 1
        print(f"  已插入 {inserted} 条 (跳过 {skipped})")


def cli_main():
    """python -m knowgraph.migration.migrate_to_mysql 入口。"""
    import argparse
    parser = argparse.ArgumentParser(description="图数据库 (Apache AGE) → MySQL 迁移")
    parser.add_argument("--dry-run", action="store_true", help="试运行")
    parser.add_argument("--limit", type=int, default=0, help="限制条数 (0=全量)")
    parser.add_argument("--clean", action="store_true", help="清空旧数据")
    args = parser.parse_args()
    GraphToMySQLMigrator(dry_run=args.dry_run, limit=args.limit, clean=args.clean).run()


if __name__ == "__main__":
    cli_main()
