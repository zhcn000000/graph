from datetime import date

from knowgraph.spider.config import MUSEUM_CONFIGS, MuseumConfig
from knowgraph.spider.models import ArtifactData, CrawlResult, SitemapUrl


class TestArtifactData:
    def test_artifact_data_defaults(self):
        data = ArtifactData()
        assert not data.object_id
        assert not data.title
        assert not data.museum

    def test_to_db_dict_basic(self):
        data = ArtifactData(
            object_id="OBJ-001",
            title="青铜鼎",
            museum="Metropolitan Museum of Art",
            detail_url="https://metmuseum.org/art/001",
        )
        db_dict = data.to_db_dict()
        assert db_dict["object_id"] == "OBJ-001"
        assert db_dict["title"] == "青铜鼎"
        assert db_dict["museum"] == "Metropolitan Museum of Art"
        assert db_dict["detail_url"] == "https://metmuseum.org/art/001"

    def test_to_db_dict_with_crawl_date(self):

        data = ArtifactData(
            museum="test",
            detail_url="https://test.com",
            crawl_date=date(2025, 1, 15),
        )
        db_dict = data.to_db_dict()
        assert db_dict["crawl_date"] == date(2025, 1, 15)

    def test_to_db_dict_without_crawl_date(self):
        data = ArtifactData(
            museum="test",
            detail_url="https://test.com",
            crawl_date=None,
        )
        db_dict = data.to_db_dict()
        assert "crawl_date" not in db_dict


class TestSitemapUrl:
    def test_sitemap_url_creation(self):
        url = SitemapUrl(
            loc="https://example.com/artifact/1",
            lastmod="2025-01-15",
            changefreq="monthly",
            priority="0.8",
        )
        assert url.loc == "https://example.com/artifact/1"
        assert url.lastmod == "2025-01-15"

    def test_sitemap_url_defaults(self):
        url = SitemapUrl(loc="https://example.com/test")
        assert url.lastmod is None
        assert url.changefreq is None
        assert url.priority is None


class TestCrawlResult:
    def test_crawl_result_defaults(self):
        result = CrawlResult()
        assert not result.museum
        assert result.total_urls == 0
        assert result.errors == 0
        assert result.error_details == []

    def test_crawl_result_with_data(self):
        result = CrawlResult(
            museum="Metropolitan Museum of Art",
            total_urls=100,
            filtered_urls=80,
            crawled_urls=50,
            stored=45,
            skipped=5,
            errors=3,
            elapsed=120.5,
            error_details=["Timeout on URL A", "404 on URL B"],
        )
        assert result.total_urls == 100
        assert result.stored == 45
        assert len(result.error_details) == 2


class TestMuseumConfig:
    def test_museum_config_creation(self):
        config = MuseumConfig(
            key="test_museum",
            name="Test Museum",
            location="Test Location",
            website="https://test.museum",
            sitemap_url="https://test.museum/sitemap.xml",
            collection_url_prefix="/collections/",
            artifact_url_patterns=["/collections/", "/objects/"],
            chinese_culture_taxonomy=["china", "chinese", "tang"],
        )
        assert config.key == "test_museum"
        assert config.name == "Test Museum"
        assert len(config.artifact_url_patterns) == 2
        assert "china" in config.chinese_culture_taxonomy

    def test_museum_config_defaults(self):
        config = MuseumConfig(
            key="test",
            name="Test",
            location="Test",
            website="https://test.com",
            sitemap_url="https://test.com/sitemap.xml",
        )
        assert not config.collection_url_prefix
        assert config.artifact_url_patterns == []
        assert config.chinese_culture_taxonomy == []


class TestMuseumConfigs:
    def test_configs_loaded(self):
        assert len(MUSEUM_CONFIGS) > 0

    def test_all_configs_have_keys(self):
        for key, config in MUSEUM_CONFIGS.items():
            assert config.key == key
            assert config.name
            assert config.sitemap_url

    def test_specific_museum(self):
        met = MUSEUM_CONFIGS["metropolitan"]
        assert met.name == "The Metropolitan Museum of Art"
        assert "metmuseum.org" in met.website

    def test_cleveland_museum(self):
        cleveland = MUSEUM_CONFIGS["cleveland"]
        assert cleveland.name == "Cleveland Museum of Art"

    def test_freer_sackler(self):
        fs = MUSEUM_CONFIGS["freer_sackler"]
        assert fs.name == "Freer Gallery of Art and Arthur M. Sackler Gallery"
