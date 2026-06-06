#!/bin/bash
# 图数据库 → MySQL 迁移
# 用法:
#   ./scripts/migrate-mysql.sh                            # 全量
#   ./scripts/migrate-mysql.sh --limit 100 --clean        # 清空后 100 条
#   ./scripts/migrate-mysql.sh --dry-run                  # 试运行
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m knowgraph.migration.migrate_to_mysql "$@"
