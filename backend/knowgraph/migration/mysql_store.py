
import pymysql
import pymysql.cursors

from knowgraph.utils.environments import settings


class MySQLStore:
    """MySQL 数据库操作封装（从 settings 读取连接信息）。"""

    def __init__(self):
        self.conn: pymysql.Connection | None = None

    def connect(self):
        self.conn = pymysql.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD.get_secret_value(),
            database=settings.MYSQL_DATABASE,
            charset="utf8mb4",
        )

    def close(self):
        if self.conn:
            self.conn.close()

    # ---- 基础操作 ----

    def execute(self, sql: str, params: tuple | None = None) -> int:
        """执行 SQL，返回 lastrowid（无自增主键则返回 rowcount）。"""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid or cur.rowcount

    def insert(self, table: str, data: dict) -> int:
        """插入一条记录。"""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def query_one(self, sql: str, params: tuple | None = None) -> dict | None:
        with self.conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def query_all(self, sql: str, params: tuple | None = None) -> list[dict]:
        with self.conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # ---- 便捷查询 ----

    def get_museum_id(self, name: str) -> int | None:
        row = self.query_one("SELECT id FROM museums WHERE name = %s", (name,))
        return row["id"] if row else None

    def get_dynasty_id(self, name_en: str) -> int | None:
        row = self.query_one("SELECT id FROM dynasties WHERE name_en = %s", (name_en,))
        return row["id"] if row else None

    def get_first_museum_id(self) -> int | None:
        row = self.query_one("SELECT id FROM museums ORDER BY id LIMIT 1")
        return row["id"] if row else None

    # ---- 表管理 ----

    def truncate_all(self):
        """清空所有表数据（用于测试）。"""
        tables = [
            "artifact_artist", "artifact_images", "artifacts",
            "artists", "dynasties", "museums",
        ]
        with self.conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for t in tables:
                cur.execute(f"TRUNCATE TABLE {t}")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        self.conn.commit()
