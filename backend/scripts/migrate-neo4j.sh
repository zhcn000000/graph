#!/bin/bash
# 图数据库三元组 → Neo4j 迁移
# 用法:
#   ./scripts/migrate-neo4j.sh                            # 全量
#   ./scripts/migrate-neo4j.sh --limit 1000 --clean       # 清空后 1000 条
#   ./scripts/migrate-neo4j.sh --dry-run                  # 试运行
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m knowgraph.migration.migrate_to_neo4j "$@"
