from uuid import UUID, uuid4

import pytest
from pydantic_ai.models.test import TestModel
from pytest_mock import MockerFixture

from knowgraph.database.document import build_artifact_triples
from knowgraph.documents.models import Document
from knowgraph.graph import RelationshipType
from knowgraph.graph.schema import (
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipInfo,
)
from knowgraph.graph.triples import LLMExtractor
from knowgraph.utils.environments import settings

TEST_CSV_ROWS = [
    {
        "object_id": "OBJ-001",
        "title": "青铜鼎",
        "period": "商朝",
        "type": "青铜器",
        "material": "青铜",
        "description": "一件商朝时期的青铜鼎，用于祭祀仪式",
        "dimensions": "高50cm，宽30cm",
        "museum": "Metropolitan Museum of Art",
        "location": "New York",
        "detail_url": "https://metmuseum.org/art/001",
        "image_url": "https://metmuseum.org/img/001.jpg",
        "credit_line": "捐赠",
        "accession_number": "ACC-001",
        "crawl_date": "2025-01-15",
    },
    {
        "object_id": "OBJ-002",
        "title": "青花瓷瓶",
        "period": "明朝",
        "type": "瓷器",
        "material": "陶瓷",
        "description": None,
        "dimensions": "高30cm",
        "museum": "Cleveland Museum of Art",
        "location": "Cleveland",
        "detail_url": "https://clevelandart.org/art/002",
        "image_url": "https://clevelandart.org/img/002.jpg",
        "credit_line": None,
        "accession_number": "ACC-002",
        "crawl_date": "2025-03-20",
    },
    {
        "object_id": "OBJ-003",
        "title": "山水画",
        "period": None,
        "type": "绘画",
        "material": "纸本",
        "description": "清代山水画",
        "dimensions": None,
        "museum": "Freer Gallery of Art",
        "location": None,
        "detail_url": "https://asia.si.edu/object/003",
        "image_url": None,
        "credit_line": None,
        "accession_number": None,
        "crawl_date": None,
    },
]


TEST_DB_NAME = "test_data"
settings.POSTGRES_DB = TEST_DB_NAME


def make_sample_vector() -> list[list[float]]:
    return [[0.1] * 1024]


def make_sample_embedding() -> list[list[float]]:
    return [[0.1] * 1024]


@pytest.fixture
def sample_document_text() -> str:
    return (
        "青铜器是中国古代文明的瑰宝。商周时期的青铜器制作工艺精湛，造型优美。"
        "这些青铜器不仅用于祭祀，还用于日常生活。青铜器的纹饰丰富多样，包括饕餮纹、云雷纹等。"
        "大都会博物馆收藏了大量中国青铜器，其中以商代青铜鼎最为著名。"
        "清代宫廷绘画以工笔重彩为主，题材广泛，包括山水、人物、花鸟等。"
        "北京故宫博物院收藏了大量清代宫廷绘画精品。"
    )


@pytest.fixture
def sample_documents(sample_document_text: str) -> list[Document]:
    return [
        Document(
            content=sample_document_text,
            name="sample_artifact.md",
            link="file:///data/sample_artifact.md",
            metadata={"file_name": "sample_artifact.md"},
        ),
        Document(
            content="明朝青花瓷以其独特的蓝色釉料闻名于世。景德镇是青花瓷的主要产地。",
            name="sample_porcelain.md",
            link="file:///data/sample_porcelain.md",
            metadata={"file_name": "sample_porcelain.md"},
        ),
    ]


@pytest.fixture
def sample_chunks(sample_document_text: str) -> list[str]:
    return [
        "青铜器是中国古代文明的瑰宝。商周时期的青铜器制作工艺精湛，造型优美。",
        "这些青铜器不仅用于祭祀，还用于日常生活。青铜器的纹饰丰富多样，包括饕餮纹、云雷纹等。",
        "大都会博物馆收藏了大量中国青铜器，其中以商代青铜鼎最为著名。",
        "清代宫廷绘画以工笔重彩为主，题材广泛，包括山水、人物、花鸟等。北京故宫博物院收藏了大量清代宫廷绘画精品。",
    ]


@pytest.fixture
def sample_entities() -> list[ExtractedTriple]:
    return [
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
            object=ExtractedEntity(name="Metropolitan Museum of Art", entity_type=EntityType.MUSEUM),
            description="青铜鼎收藏于Metropolitan Museum of Art",
        ),
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.BELONGS_TO_DYNASTY),
            object=ExtractedEntity(name="商朝", entity_type=EntityType.DYNASTY),
            description="青铜鼎属于商朝",
        ),
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.MADE_OF_MATERIAL),
            object=ExtractedEntity(name="青铜", entity_type=EntityType.MATERIAL),
            description="青铜鼎材质为青铜",
        ),
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.IS_TYPE_OF),
            object=ExtractedEntity(name="青铜器", entity_type=EntityType.ARTIFACT_TYPE),
            description="青铜鼎类型为青铜器",
        ),
    ]


@pytest.fixture
def sample_entities_from_csv() -> list[ExtractedTriple]:
    triples: list[ExtractedTriple] = []
    for row_dict in TEST_CSV_ROWS:
        triples.extend(build_artifact_triples(row_dict))
    return triples


@pytest.fixture
def mock_llm_extractor(mocker: MockerFixture):
    mock_agent = mocker.AsyncMock(return_value=[])
    with mocker.patch.object(LLMExtractor, "_run_agent_with_prompt", mock_agent):
        yield mock_agent


@pytest.fixture
def test_model(sample_entities: list[ExtractedTriple]) -> TestModel:
    return TestModel(custom_output_args=sample_entities)


@pytest.fixture
def mock_uuid_list() -> list[UUID]:
    return [uuid4() for _ in range(5)]


@pytest.fixture
def source_id() -> UUID:
    return uuid4()


@pytest.fixture(scope="session")
async def setup_test_database():
    """Session-scoped fixture: creates and initializes the test database once."""
    from knowgraph.database.initdb import init_db

    await init_db(alter_system=False, dbname=TEST_DB_NAME)


@pytest.fixture
async def clean_tables():
    """Function-scoped fixture: clean all tables between tests.

    Depends on setup_test_database to ensure the database exists.
    """
    from knowgraph.database.database import DatabaseManager
    from knowgraph.database.graph import AgeGraphManager

    db = DatabaseManager(TEST_DB_NAME)
    await db.adrop_all()
    await db.acreate_all()
    graph = AgeGraphManager(TEST_DB_NAME)
    await graph.adrop_graph()
    await graph.acreate_graph()


@pytest.fixture
async def clean_test_database():
    """Function-scoped fixture: drops and recreates the entire test database."""
    from knowgraph.database.initdb import clean_db

    await clean_db(dbname=TEST_DB_NAME, force=True)


@pytest.fixture
async def reset_test_database():
    """Function-scoped fixture: resets the test database by dropping and recreating it."""
    from knowgraph.database.initdb import reset_db

    await reset_db(dbname=TEST_DB_NAME, force=True)
