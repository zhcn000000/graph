from dataclasses import dataclass, field


@dataclass
class MuseumConfig:
    key: str
    name: str
    location: str
    website: str
    sitemap_url: str
    collection_url_prefix: str = ""
    artifact_url_patterns: list[str] = field(default_factory=list)
    chinese_culture_taxonomy: list[str] = field(default_factory=list)


MUSEUM_CONFIGS: dict[str, MuseumConfig] = {
    "cleveland": MuseumConfig(
        key="cleveland",
        name="Cleveland Museum of Art",
        location="Cleveland, Ohio, USA",
        website="https://www.clevelandart.org",
        sitemap_url="https://www.clevelandart.org/robots.txt",
        collection_url_prefix="/art/",
        artifact_url_patterns=["/art/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),
    "metropolitan": MuseumConfig(
        key="metropolitan",
        name="The Metropolitan Museum of Art",
        location="New York, USA",
        website="https://www.metmuseum.org",
        sitemap_url="https://www.metmuseum.org/robots.txt",
        collection_url_prefix="/art/collection/search/",
        artifact_url_patterns=["/art/collection/search/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),
    "smithsonian": MuseumConfig(
        key="smithsonian",
        name="Smithsonian Institution",
        location="Washington, D.C., USA",
        website="https://www.si.edu",
        sitemap_url="https://www.si.edu/sitemap.xml",
        collection_url_prefix="/object/",
        artifact_url_patterns=["/object/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),  # cloudflare protected
    "freer_sackler": MuseumConfig(
        key="freer_sackler",
        name="Freer Gallery of Art and Arthur M. Sackler Gallery",
        location="Washington, D.C., USA",
        website="https://asia.si.edu",
        sitemap_url="https://asia.si.edu/sitemap.xml",
        collection_url_prefix="/object/",
        artifact_url_patterns=["/object/", "/collections/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),  # cloudflare protected
    "princeton": MuseumConfig(
        key="princeton",
        name="Princeton University Art Museum",
        location="Princeton, New Jersey, USA",
        website="https://artmuseum.princeton.edu",
        sitemap_url="https://artmuseum.princeton.edu/sitemap.xml",
        collection_url_prefix="/collections/",
        artifact_url_patterns=["/collections/", "/objects/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),
    "nelson_atkins": MuseumConfig(
        key="nelson_atkins",
        name="The Nelson-Atkins Museum of Art",
        location="Kansas City, Missouri, USA",
        website="https://art.nelson-atkins.org",
        sitemap_url="https://art.nelson-atkins.org/sitemap.xml",
        collection_url_prefix="/collections/",
        artifact_url_patterns=["/collections/", "/objects/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),
    # "asian_art_sf": MuseumConfig(
    #     key="asian_art_sf",
    #     name="Asian Art Museum of San Francisco",
    #     location="San Francisco, California, USA",
    #     website="https://searchcollection.asianart.org",
    #     sitemap_url="https://searchcollection.asianart.org/robots.txt",
    #     collection_url_prefix="/objects/",
    #     artifact_url_patterns=["/objects/"],
    #     chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    # ),
    # block by captcha,
    # "mfa_boston": MuseumConfig(
    #     key="mfa_boston",
    #     name="Museum of Fine Arts, Boston",
    #     location="Boston, Massachusetts, USA",
    #     website="https://www.mfa.org",
    #     sitemap_url="https://www.mfa.org/sitemap.xml",
    #     collection_url_prefix="/collections/object/",
    #     artifact_url_patterns=["/collections/object/"],
    #     chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    # ),
    # no sitemap, and block by captcha,
    # "minneapolis": MuseumConfig(
    #     key="minneapolis",
    #     name="Minneapolis Institute of Art",
    #     location="Minneapolis, Minnesota, USA",
    #     website="https://collections.artsmia.org",
    #     sitemap_url="https://collections.artsmia.org/sitemap.xml",
    #     collection_url_prefix="/art/",
    #     artifact_url_patterns=["/art/"],
    #     chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    # ),
    # no sitemap.
    "artic": MuseumConfig(
        key="artic",
        name="Art Institute of Chicago",
        location="Chicago, Illinois, USA",
        website="https://www.artic.edu",
        sitemap_url="https://www.artic.edu/sitemap.xml",
        collection_url_prefix="/artworks/",
        artifact_url_patterns=["/artworks/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),  # cloudflare protected
    # "penn_museum": MuseumConfig(
    #     key="penn_museum",
    #     name="Penn Museum",
    #     location="Philadelphia, Pennsylvania, USA",
    #     website="https://www.penn.museum",
    #     sitemap_url="https://www.penn.museum/sitemap.xml",
    #     collection_url_prefix="/collections/object/",
    #     artifact_url_patterns=["/collections/object/"],
    #     chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    # ),
    # no sitemap,
    "philadelphia": MuseumConfig(
        key="philadelphia",
        name="Philadelphia Museum of Art",
        location="Philadelphia, Pennsylvania, USA",
        website="https://www.philamuseum.org",
        sitemap_url="https://www.philamuseum.org/robots.txt",
        collection_url_prefix="/collections/",
        artifact_url_patterns=["/collections/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),
    # no sitemap,
    # "harvard": MuseumConfig(
    #     key="harvard",
    #     name="Harvard Art Museums",
    #     location="Cambridge, Massachusetts, USA",
    #     website="https://harvardartmuseums.org",
    #     sitemap_url="https://harvardartmuseums.org/sitemap.xml",
    #     collection_url_prefix="/collections/object/",
    #     artifact_url_patterns=["/collections/object/"],
    #     chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    # ),
    # no sitemap,no allow crawl.
    "amnh": MuseumConfig(
        key="amnh",
        name="American Museum of Natural History",
        location="New York, USA",
        website="https://anthro.amnh.org",
        sitemap_url="https://www.amnh.org/robots.txt",
        collection_url_prefix="/collections/",
        artifact_url_patterns=["/collections/"],
        chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    ),
    # "brooklyn": MuseumConfig(
    #     key="brooklyn",
    #     name="Brooklyn Museum",
    #     location="Brooklyn, New York, USA",
    #     website="https://www.brooklynmuseum.org",
    #     sitemap_url="https://www.brooklynmuseum.org/sitemap.xml",
    #     collection_url_prefix="/opencollection/objects/",
    #     artifact_url_patterns=["/opencollection/objects/"],
    #     chinese_culture_taxonomy=["china", "chinese", "chin", "tang", "song", "ming", "qing", "yuan", "han"],
    # ),
    # no sitemap.
}
