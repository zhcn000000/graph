"""
三元组建模模块
从MySQL数据生成知识图谱三元组，用于Neo4j导入和链接开放数据
"""
import os
import csv
import logging
from typing import List, Dict, Tuple

import config

logger = logging.getLogger(__name__)


class TripleBuilder:
    """知识图谱三元组建模器"""

    def __init__(self):
        self.triples: List[Tuple[str, str, str]] = []

    def build_from_dataframes(self, all_data: dict, dynasty_data: list, museums: dict) -> List[Tuple[str, str, str]]:
        """
        从数据构建三元组
        三元组格式: (主语, 谓语, 宾语)

        关系类型:
        - (文物, 藏于, 博物馆)
        - (文物, 属于朝代, 朝代)
        - (文物, 材质为, 材质)
        - (文物, 类型为, 类型)
        - (文物, 由...创作, 艺术家)
        - (朝代, 起始于, 年份)
        - (朝代, 结束于, 年份)
        """
        self.triples = []

        for museum_key, df in all_data.items():
            museum_info = museums.get(museum_key, {})
            museum_name = museum_info.get("name", museum_key)

            for _, row in df.iterrows():
                obj_id = str(row.get("object_id", ""))
                title = str(row.get("title_en", ""))
                if not obj_id:
                    continue

                artifact_uri = f"artifact:{obj_id}"

                # (文物, 藏于, 博物馆)
                self.triples.append((artifact_uri, "stored_in", f"museum:{museum_name}"))

                # (文物, 属于朝代, 朝代)
                dynasty = str(row.get("dynasty", "")).strip()
                if dynasty and dynasty not in ("", "nan"):
                    self.triples.append((artifact_uri, "belongs_to_dynasty", f"dynasty:{dynasty}"))

                # (文物, 材质为, 材质)
                material = str(row.get("material", "")).strip()
                if material and material not in ("", "nan"):
                    self.triples.append((artifact_uri, "made_of", f"material:{material}"))

                # (文物, 类型为, 类型)
                art_type = str(row.get("type", "")).strip()
                if art_type and art_type not in ("", "nan"):
                    self.triples.append((artifact_uri, "classified_as", f"type:{art_type}"))

                # (文物, 由...创作, 艺术家)
                artist = str(row.get("artist", "")).strip()
                if artist and artist.lower() not in ("artist/maker unknown", "unknown", "", "nan"):
                    self.triples.append((artifact_uri, "created_by", f"artist:{artist}"))

                # (文物, 产于, 地点/国家)
                country = str(row.get("country", "")).strip()
                if country and country not in ("", "nan"):
                    self.triples.append((artifact_uri, "produced_in", f"location:{country}"))

        # 朝代三元组
        for d in dynasty_data:
            dynasty_uri = f"dynasty:{d['name_en']}"
            self.triples.append((dynasty_uri, "start_year", str(d["start_year"])))
            self.triples.append((dynasty_uri, "end_year", str(d["end_year"])))
            self.triples.append((dynasty_uri, "name_zh", d["name_zh"]))

        logger.info(f"生成三元组: {len(self.triples)} 个")
        return self.triples

    def save_to_csv(self, output_path: str = None):
        """保存三元组到CSV文件"""
        if output_path is None:
            output_path = os.path.join(config.DATA_DIR, "triples.csv")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["subject", "predicate", "object"])
            for s, p, o in self.triples:
                writer.writerow([s, p, o])

        logger.info(f"三元组保存到: {output_path} ({len(self.triples)} 个)")

    def save_as_rdf(self, output_path: str = None):
        """保存为简单的RDF/N-Triples格式（链接开放数据）"""
        if output_path is None:
            output_path = os.path.join(config.DATA_DIR, "triples.nt")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        base_uri = "http://example.org/overseas-chinese-artifacts/"

        with open(output_path, "w", encoding="utf-8") as f:
            for s, p, o in self.triples:
                # N-Triples格式: <subject> <predicate> <object> .
                subj = f"<{base_uri}{s.replace(':', '/')}>"
                pred = f"<{base_uri}{p}>"
                if o.startswith(("artifact:", "museum:", "dynasty:", "material:", "type:", "artist:", "location:")):
                    obj = f"<{base_uri}{o.replace(':', '/')}>"
                else:
                    obj = f'"{o}"'
                f.write(f"{subj} {pred} {obj} .\n")

        logger.info(f"RDF三元组保存到: {output_path}")
