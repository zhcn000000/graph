import json
from collections import Counter
from datetime import datetime

from knowgraph.migration.graph_reader import AGEGraphReader
from knowgraph.migration.neo4j_writer import Neo4jWriter


class TriplesMigrator:
    """AGE → Neo4j 三元组迁移编排器。"""

    def __init__(self, dry_run: bool = False, limit: int = 0, clean: bool = False):
        self.dry_run = dry_run
        self.limit = limit
        self.clean = clean
        self.reader: AGEGraphReader | None = None
        self.writer: Neo4jWriter | None = None

    def run(self) -> int:
        start = datetime.now()
        self._print_header()

        self.reader = AGEGraphReader()
        self.reader.connect()
        node_count = self.reader.count_nodes()
        rel_count = self.reader.count_rels()
        print(f"[PG] 连接成功, 共 {node_count} 个节点, {rel_count} 条关系")

        self.writer = Neo4jWriter(dry_run=self.dry_run)
        self.writer.connect()
        if not self.dry_run:
            print("[Neo4j] 连接成功")

        try:
            if self.clean and not self.dry_run:
                print("\n[准备] 清空 Neo4j...")
                self.writer.clear_all()

            print("\n[Step 1/3] 创建唯一约束...")
            self.writer.create_constraints()

            print("\n[Step 2/3] 迁移节点...")
            self._migrate_nodes()

            print("\n[Step 3/3] 迁移关系 (三元组)...")
            self._migrate_relationships()
        except Exception:
            import traceback
            traceback.print_exc()
            return 1
        finally:
            self.reader.close()
            self.writer.close()

        elapsed = (datetime.now() - start).total_seconds()
        print("\n" + "=" * 60)
        print("迁移完成")
        print("=" * 60)
        print(f"  节点:   {self.writer.nodes_written}")
        print(f"  关系:   {self.writer.rels_written}")
        print(f"  总耗时: {elapsed:.1f} 秒")
        if not self.dry_run:
            self._print_connection_info()
        return 0

    def _print_header(self):
        print("=" * 60)
        print("Apache AGE → Neo4j 三元组迁移")
        print("=" * 60)
        print(f"  试运行: {'是' if self.dry_run else '否'}")
        print(f"  限制:   {self.limit} 条三元组" if self.limit > 0 else "  限制:   全量")
        print(f"  清空:   {'是' if self.clean else '否'}")
        print()

    def _print_connection_info(self):
        from knowgraph.utils.environments import settings as s
        print("\nNeo4j 连接信息:")
        print(f"  Bolt: {s.NEO4J_URI}")
        print(f"  User: {s.NEO4J_USER}")

    def _migrate_nodes(self):
        raw_nodes = self.reader.get_all_nodes()
        print(f"  从 AGE 读取到 {len(raw_nodes)} 个节点")

        nodes: list[dict] = []
        skipped = 0
        for n in raw_nodes:
            name = n.get("name")
            if not name or not str(name).strip():
                skipped += 1
                continue
            labels = n.get("labels")
            if isinstance(labels, str):
                try:
                    labels = json.loads(labels)
                except (json.JSONDecodeError, TypeError):
                    labels = [labels]
            label = labels[0] if labels else "Entity"
            nodes.append({
                "label": label,
                "entity_type": n.get("entity_type") or label.lower(),
                "name": str(name).strip(),
            })
        if skipped:
            print(f"    跳过 {skipped} 个无效节点")

        label_counts = Counter(n["label"] for n in nodes)
        for label, cnt in label_counts.most_common():
            print(f"    {label}: {cnt}")

        if self.dry_run:
            print(f"  [DRY RUN] 将写入 {len(nodes)} 个节点")
            self.writer.write_nodes(nodes)
            return

        batch_size = 5000
        total = 0
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            n = self.writer.write_nodes(batch)
            total += n
            if len(nodes) > batch_size:
                print(f"    已写入 {total}/{len(nodes)} 节点...")
        print(f"  已写入 {total} 个节点")

    def _migrate_relationships(self):
        raw_rels = self.reader.get_all_relationships()
        print(f"  从 AGE 读取到 {len(raw_rels)} 条关系")

        rels: list[dict] = []
        rel_skipped = 0
        for r in raw_rels:
            s_name = r.get("s_name", "")
            o_name = r.get("o_name", "")
            if not s_name or not str(s_name).strip() or not o_name or not str(o_name).strip():
                rel_skipped += 1
                continue
            s_labels = r.get("s_labels")
            if isinstance(s_labels, str):
                try:
                    s_labels = json.loads(s_labels)
                except (json.JSONDecodeError, TypeError):
                    s_labels = [s_labels]
            o_labels = r.get("o_labels")
            if isinstance(o_labels, str):
                try:
                    o_labels = json.loads(o_labels)
                except (json.JSONDecodeError, TypeError):
                    o_labels = [o_labels]
            rels.append({
                "s_label": s_labels[0] if s_labels else "Entity",
                "s_name": str(s_name).strip(),
                "predicate": r.get("predicate", ""),
                "o_label": o_labels[0] if o_labels else "Entity",
                "o_name": str(o_name).strip(),
            })
        if rel_skipped:
            print(f"    跳过 {rel_skipped} 条无效关系")

        if self.limit > 0 and len(rels) > self.limit:
            rels = rels[:self.limit]
            print(f"  限制为 {self.limit} 条")

        pred_counts = Counter(r["predicate"] for r in rels)
        for pred, cnt in pred_counts.most_common():
            print(f"    {pred}: {cnt}")

        if self.dry_run:
            print(f"  [DRY RUN] 将写入 {len(rels)} 条")
            self.writer.write_relationships(rels)
            return

        batch_size = 2000
        total = 0
        for i in range(0, len(rels), batch_size):
            batch = rels[i : i + batch_size]
            n = self.writer.write_relationships(batch)
            total += n
            if len(rels) > batch_size:
                print(f"    已写入 {total}/{len(rels)} 条关系...")
        print(f"  已写入 {total} 条关系")


def cli_main():
    """python -m knowgraph.migration.migrate_to_neo4j 入口。"""
    import argparse
    parser = argparse.ArgumentParser(description="AGE → Neo4j 三元组迁移")
    parser.add_argument("--dry-run", action="store_true", help="试运行")
    parser.add_argument("--limit", type=int, default=0, help="限制条数 (0=全量)")
    parser.add_argument("--clean", action="store_true", help="清空旧数据")
    args = parser.parse_args()
    TriplesMigrator(dry_run=args.dry_run, limit=args.limit, clean=args.clean).run()


if __name__ == "__main__":
    cli_main()
