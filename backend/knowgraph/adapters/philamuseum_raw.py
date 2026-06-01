
import pandas as pd

from .base import BaseAdapter, safe_str

REQUIRED_FIELDS = ("详情链接", "藏品名称")


class PhilaMuseumRawAdapter(BaseAdapter):
    name = "philamuseum_raw"

    def __init__(self, museum: str = "Philadelphia Museum of Art") -> None:
        super().__init__()
        self.museum = museum

    def validate_row(self, row: dict) -> bool:
        return all(pd.notna(row.get(f)) for f in REQUIRED_FIELDS)

    def row_to_dict(self, row: dict) -> dict:
        dynasty = safe_str(row.get("朝代"))
        time_period = safe_str(row.get("时间"))
        period = dynasty or time_period
        if dynasty and time_period:
            period = f"{dynasty} ({time_period})"

        return {
            "object_id": safe_str(row.get("藏品编号")),
            "title": safe_str(row.get("藏品名称")),
            "period": period,
            "type": safe_str(row.get("类别")),
            "material": safe_str(row.get("媒介")),
            "description": safe_str(row.get("摘要")),
            "dimensions": safe_str(row.get("尺寸")),
            "museum": self.museum,
            "location": "",
            "detail_url": safe_str(row.get("详情链接")),
            "image_url": safe_str(row.get("图片链接")),
            "credit_line": safe_str(row.get("信用信息")),
            "accession_number": "",
            "crawl_date": "",
        }
