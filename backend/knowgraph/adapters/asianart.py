import pandas as pd

from .base import BaseAdapter, safe_str

REQUIRED_FIELDS = ("detail_url", "Title")


class AsianArtAdapter(BaseAdapter):
    name = "asianart"
    default_csv = "objects_china_verified_dedup.csv"

    museum_name = "Asian Art Museum"

    def validate_row(self, row: dict) -> bool:
        return all(pd.notna(row.get(f)) for f in REQUIRED_FIELDS)

    def row_to_dict(self, row: dict) -> dict:
        date_val = safe_str(row.get("Date"))
        dynasty = safe_str(row.get("Dynasty"))
        period = safe_str(row.get("Period"))
        parts = [p for p in (period, dynasty, date_val) if p]
        combined_period = "; ".join(parts) if parts else ""

        return {
            "object_id": safe_str(row.get("Object number")),
            "title": safe_str(row.get("Title")),
            "period": combined_period,
            "type": safe_str(row.get("Classifications")),
            "material": safe_str(row.get("Materials")) or safe_str(row.get("Medium")),
            "description": "",
            "dimensions": safe_str(row.get("Dimensions")),
            "museum": self.museum_name,
            "location": safe_str(row.get("Place of Origin")) or safe_str(row.get("Culture")),
            "detail_url": safe_str(row.get("detail_url")),
            "image_url": safe_str(row.get("image_url")),
            "credit_line": safe_str(row.get("Credit Line")),
            "accession_number": safe_str(row.get("Object number")),
            "artist": safe_str(row.get("Artist")),
            "crawl_date": "",
        }
