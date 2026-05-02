from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup
from scrapy.spiders import SitemapSpider

from ..database.artifact import ArtifactStore
from .config import MuseumConfig
from .filter import ChineseArtifactFilter


class ArtifactSitemapSpider(SitemapSpider):
    name = "artifact_spider"

    def __init__(
        self,
        museum_config: MuseumConfig | None = None,
        chinese_filter: ChineseArtifactFilter | None = None,
        artifact_store: ArtifactStore | None = None,
        stats_collector: dict | None = None,
        **kwargs: Any,
    ) -> None:
        self._filter = chinese_filter or ChineseArtifactFilter()
        self.artifact_store = artifact_store or ArtifactStore()
        self.stats_collector = stats_collector or {}
        self.stats: dict[str, int] = {"stored": 0, "skipped": 0, "errors": 0, "parsed": 0}

        if museum_config is not None:
            rules: list[tuple[str, str]] = []
            for pattern in museum_config.artifact_url_patterns or []:
                rules.append((re.escape(pattern), "parse_artifact"))
            if not rules:
                rules = [(".*", "parse_artifact")]
            kwargs["sitemap_urls"] = [museum_config.sitemap_url]
            kwargs["sitemap_rules"] = rules
            self._museum_config = museum_config

        super().__init__(**kwargs)

    def _get_config(self) -> MuseumConfig | None:
        return getattr(self, "_museum_config", None)

    def closed(self, reason: str) -> None:
        self.stats_collector.update(self.stats)

    async def parse_artifact(self, response):
        self.stats["parsed"] += 1
        config = self._get_config()
        museum_name = config.name if config else ""
        museum_location = config.location if config else ""

        data = self._extract_data(response, museum_name, museum_location, response.url)
        if data is None:
            self.stats["errors"] += 1
            return

        if not self._filter.check_content(
            title=data.get("title", ""),
            description=data.get("description", ""),
            culture=data.get("extra", {}).get("culture", ""),
            period=data.get("period", ""),
            material=data.get("material", ""),
            config=config,
        ):
            self.stats["skipped"] += 1
            return

        self.stats["stored"] += 1
        yield {
            "object_id": data.get("object_id", ""),
            "title": data.get("title", ""),
            "period": data.get("period", ""),
            "type": data.get("type", ""),
            "material": data.get("material", ""),
            "description": data.get("description", ""),
            "dimensions": data.get("dimensions", ""),
            "museum": data.get("museum", museum_name),
            "location": data.get("location", museum_location),
            "detail_url": data.get("detail_url", response.url),
            "image_url": data.get("image_url", ""),
            "image_path": data.get("image_path", ""),
            "credit_line": data.get("credit_line", ""),
            "accession_number": data.get("accession_number", ""),
            "crawl_date": date.today(),
        }

    @staticmethod
    def _extract_data(
        response,
        museum: str = "",
        location: str = "",
        detail_url: str = "",
    ) -> dict | None:
        soup = BeautifulSoup(response.text, "lxml")

        title = ""
        description = ""
        image_url = ""
        extra: dict = {}

        ld_data = _parse_jsonld(soup)
        if ld_data:
            title = ld_data.get("name", "")
            description = ld_data.get("description", "")
            image_url = ld_data.get("image", "")
            extra = ld_data

        if not title:
            title = _meta_content(soup, "og:title") or _meta_content(soup, "title")
            if not title:
                tag = soup.find("title")
                title = tag.get_text(strip=True) if tag else ""
                parts = title.rsplit("|", 1)
                if len(parts) > 1 and len(parts[1].strip()) < len(parts[0].strip()):
                    title = parts[0].strip()

        if not description:
            description = _meta_content(soup, "og:description") or _meta_content(soup, "description")

        if not image_url:
            image_url = _meta_content(soup, "og:image") or _find_image(soup, detail_url)

        accession = _find_accession(soup)

        return {
            "title": _clean_text(title),
            "description": _clean_text(description),
            "image_url": image_url,
            "detail_url": detail_url,
            "museum": museum,
            "location": location,
            "accession_number": accession,
            "extra": extra,
        }


def _parse_jsonld(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            ld = json.loads(script.string)
        except json.JSONDecodeError, TypeError:
            continue
        if isinstance(ld, dict):
            graph = ld.get("@graph", [ld])
            if isinstance(graph, list):
                for item in graph:
                    if isinstance(item, dict) and item.get("@type") in {
                        "VisualArtwork",
                        "CreativeWork",
                        "Artwork",
                        "Sculpture",
                        "Painting",
                    }:
                        return {
                            "name": _str_val(item, "name"),
                            "description": _str_val(item, "description"),
                            "image": _image_from_ld(item),
                            "credit_line": _str_val(item, "creditText"),
                            "material": _str_val(item, "artMedium") or _str_val(item, "material"),
                            "period": _str_val(item, "dateCreated"),
                            "extra": item,
                        }
    return None


def _image_from_ld(item: dict) -> str:
    img = item.get("image", "")
    if isinstance(img, str):
        return img
    if isinstance(img, list) and img:
        first = img[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("url", first.get("contentUrl", "")))
    if isinstance(img, dict):
        return str(img.get("url", img.get("contentUrl", "")))
    return ""


def _meta_content(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
    if tag:
        content = tag.get("content", "")
        return str(content).strip() if content else ""
    return ""


def _find_image(soup: BeautifulSoup, base_url: str) -> str:
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not isinstance(src, str) or not src:
            continue
        lower = src.lower()
        if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
            if "icon" not in lower and "logo" not in lower and "thumb" not in lower:
                if src.startswith("//"):
                    return f"https:{src}"
                if src.startswith("/"):
                    return f"{base_url.rstrip('/')}/{src.lstrip('/')}"
                return src
    return ""


def _find_accession(soup: BeautifulSoup) -> str:
    text = soup.get_text()
    match = re.search(r"[Aa]ccession\s*[Nn]umber[:\s]*([\w.]+)", text)
    if match:
        return match.group(1).strip()
    return ""


def _clean_text(text: str) -> str:
    clean = re.compile(r"<[^>]+>")
    return re.sub(r"\s+", " ", clean.sub("", text)).strip()


def _str_val(data: dict, key: str) -> str:
    val = data.get(key, "")
    return str(val) if val else ""
