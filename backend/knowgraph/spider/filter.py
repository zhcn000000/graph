import re

from .config import MuseumConfig


class ChineseArtifactFilter:
    def __init__(self) -> None:
        self._title_keywords = re.compile(
            r"\b(?:"
            r"chinese|china\b|chinese art|"
            r"tang dynasty|song dynasty|ming dynasty|qing dynasty|yuan dynasty|han dynasty|"
            r"shang dynasty|zhou dynasty|sui dynasty|jin dynasty|"
            r"tang chao|song chao|ming chao|qing chao|yuan chao|"
            r"jade|porcelain|celadon|bronze.*china|chinese.*ceramic|"
            r"silk road|lacquer.*china"
            r")\b",
            re.IGNORECASE,
        )
        self._desc_keywords = re.compile(
            r"\b(?:"
            r"chinese\b|china\b|dynasty.*china|"
            r"tang dynasty|song dynasty|ming dynasty|qing dynasty|yuan dynasty|han dynasty|"
            r"peking|beijing|nanjing|xi[\'']?an|canton|guangzhou|shanghai|"
            r"silk road|oriental.*china"
            r")\b",
            re.IGNORECASE,
        )
        self._url_keywords = re.compile(
            r"(?:"
            r"/chinese|/china|/chin[^a-z]|"
            r"/tang-dynasty|/song-dynasty|/ming-dynasty|/qing-dynasty|/yuan-dynasty|/han-dynasty|"
            r"/asian-art|/east-asian"
            r")",
            re.IGNORECASE,
        )
        self._culture_keywords = re.compile(
            r"\b(?:chinese|china|chin)\b",
            re.IGNORECASE,
        )

    def check_url(self, url: str) -> bool:
        if self._url_keywords.search(url):
            return True
        url_lower = url.lower()
        museum_patterns = [
            "clevelandart",
            "metmuseum",
            "si.edu",
            "asia.si.edu",
            "artmuseum.princeton",
            "nelson-atkins",
            "asianart.org",
            "mfa.org",
            "artsmia.org",
            "artic.edu",
            "penn.museum",
            "philamuseum",
            "harvardartmuseums",
            "amnh.org",
            "brooklynmuseum",
        ]
        return any(p in url_lower for p in museum_patterns)

    def check_content(
        self,
        title: str = "",
        description: str = "",
        culture: str = "",
        period: str = "",
        material: str = "",
        config: MuseumConfig | None = None,
    ) -> bool:
        if culture and self._culture_keywords.search(culture):
            return True

        combined = f"{title} {description} {period} {material}"
        if self._title_keywords.search(title) or self._desc_keywords.search(combined):
            return True

        if config and config.chinese_culture_taxonomy:
            combined_lower = combined.lower()
            for keyword in config.chinese_culture_taxonomy:
                if keyword in combined_lower:
                    return True

        return False
