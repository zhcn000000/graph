from dataclasses import dataclass, field
from datetime import date


@dataclass
class SitemapUrl:
    loc: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: str | None = None


@dataclass
class ArtifactData:
    object_id: str = ""
    title: str = ""
    period: str = ""
    type: str = ""
    material: str = ""
    description: str = ""
    dimensions: str = ""
    museum: str = ""
    location: str = ""
    detail_url: str = ""
    image_url: str = ""
    credit_line: str = ""
    accession_number: str = ""
    crawl_date: date | None = None
    extra: dict = field(default_factory=dict)

    def to_db_dict(self) -> dict[str, str | date]:
        result: dict[str, str | date] = {
            "object_id": self.object_id,
            "title": self.title,
            "period": self.period,
            "type": self.type,
            "material": self.material,
            "description": self.description,
            "dimensions": self.dimensions,
            "museum": self.museum,
            "location": self.location,
            "detail_url": self.detail_url,
            "image_url": self.image_url,
            "credit_line": self.credit_line,
            "accession_number": self.accession_number,
        }
        if self.crawl_date is not None:
            result["crawl_date"] = self.crawl_date
        return result


@dataclass
class CrawlResult:
    museum: str = ""
    total_urls: int = 0
    filtered_urls: int = 0
    crawled_urls: int = 0
    stored: int = 0
    skipped: int = 0
    errors: int = 0
    elapsed: float = 0.0
    error_details: list[str] = field(default_factory=list)
