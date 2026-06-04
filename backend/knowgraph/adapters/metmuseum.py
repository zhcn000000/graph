import pandas as pd

from .base import BaseAdapter, safe_str

REQUIRED_FIELDS = ("Object URL", "Title")


class MetMuseumAdapter(BaseAdapter):
    name = "metmuseum"
    default_csv = "daduhui.csv"

    museum_name = "Metropolitan Museum of Art"

    def validate_row(self, row: dict) -> bool:
        return all(pd.notna(row.get(f)) for f in REQUIRED_FIELDS)

    def row_to_dict(self, row: dict) -> dict:
        image = safe_str(row.get("Image"))
        image_dl = safe_str(row.get("Image Download Link"))

        if image_dl and image_dl != "unknown":
            image_url = image_dl
        elif image and image != "no_image":
            image_url = image
        else:
            image_url = ""

        return {
            "object_id": safe_str(row.get("Object ID")),
            "title": safe_str(row.get("Title")),
            "period": safe_str(row.get("Period")),
            "type": "",
            "material": safe_str(row.get("Medium")),
            "description": "",
            "dimensions": "",
            "museum": self.museum_name,
            "location": "",
            "detail_url": safe_str(row.get("Object URL")),
            "image_url": image_url,
            "credit_line": "",
            "accession_number": "",
            "artist": safe_str(row.get("Artist")),
            "crawl_date": "",
        }
