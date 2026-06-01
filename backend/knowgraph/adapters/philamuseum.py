from pathlib import Path

import pandas as pd

from .base import BaseAdapter, safe_str

DYN_ID = "dynasty_id"
MUS_ID = "museum_id"
PERIOD = "time_period"
TITLE_ZH = "title_zh"
TITLE_EN = "title_en"
REQUIRED_FIELDS = ("title_en", "detail_url", "museum_id")


class PhilaMuseumAdapter(BaseAdapter):
    name = "philamuseum"

    def __init__(self, data_dir: str | Path | None = None) -> None:
        super().__init__()
        self._dynasties: dict[int, str] = {}
        self._museums: dict[int, str] = {}
        if data_dir is not None:
            self._base = Path(data_dir)
        else:
            self._base = Path(__file__).resolve().parent.parent.parent / "philamuseum"

    def load_references(self) -> None:
        df_dyn = pd.read_csv(self._base / "clean_dynasties.csv")
        self._dynasties = dict(zip(df_dyn["id"], df_dyn["name_en"], strict=False))

        df_mus = pd.read_csv(self._base / "clean_museums.csv")
        self._museums = dict(zip(df_mus["id"], df_mus["name"], strict=False))

    def validate_row(self, row: dict) -> bool:
        return all(pd.notna(row.get(f)) for f in REQUIRED_FIELDS)

    def row_to_dict(self, row: dict) -> dict:
        title = safe_str(row.get(TITLE_ZH)) or safe_str(row.get(TITLE_EN))

        dynasty_id = row.get(DYN_ID)
        period = ""
        if pd.notna(dynasty_id) and int(dynasty_id) in self._dynasties:  # type: ignore
            period = self._dynasties[int(dynasty_id)]  # type: ignore
        if not period:
            period = safe_str(row.get(PERIOD))

        museum_id = row.get(MUS_ID)
        museum = self._museums.get(int(museum_id), "") if pd.notna(museum_id) else ""  # type: ignore

        return {
            "object_id": safe_str(row.get("object_id")),
            "title": title,
            "period": period,
            "type": safe_str(row.get("type")),
            "material": safe_str(row.get("material")),
            "description": safe_str(row.get("description")),
            "dimensions": safe_str(row.get("dimensions")),
            "museum": museum,
            "location": safe_str(row.get("location")),
            "detail_url": safe_str(row.get("detail_url")),
            "image_url": safe_str(row.get("image_url")),
            "credit_line": safe_str(row.get("credit_line")),
            "accession_number": safe_str(row.get("accession_number")),
            "crawl_date": safe_str(row.get("crawl_date")),
        }

    def load_csv(self, path: str | Path) -> list[dict]:
        self.load_references()
        return super().load_csv(path)
