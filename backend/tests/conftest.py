import os

from pytest_mock import MockerFixture

# Set test database name BEFORE any knowgraph module imports
os.environ["POSTGRES_DB"] = "test_data"

from collections import Counter
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest

from knowgraph.documents.models import Document
from knowgraph.graph.schema import (
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipType,
)

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
            predicate=RelationshipType.COLLECTED_BY,
            object=ExtractedEntity(name="Metropolitan Museum of Art", entity_type=EntityType.MUSEUM),
            description="青铜鼎收藏于Metropolitan Museum of Art",
        ),
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipType.BELONGS_TO_DYNASTY,
            object=ExtractedEntity(name="商朝", entity_type=EntityType.DYNASTY),
            description="青铜鼎属于商朝",
        ),
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipType.MADE_OF_MATERIAL,
            object=ExtractedEntity(name="青铜", entity_type=EntityType.MATERIAL),
            description="青铜鼎材质为青铜",
        ),
        ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipType.IS_TYPE_OF,
            object=ExtractedEntity(name="青铜器", entity_type=EntityType.ARTIFACT_TYPE),
            description="青铜鼎类型为青铜器",
        ),
    ]


@pytest.fixture
def mock_uuid_list() -> list[UUID]:
    return [uuid4() for _ in range(5)]


@pytest.fixture
def source_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_db_session(mocker: MockerFixture):
    """Creates a mock SQLAlchemy async session using pytest-mock."""
    session = mocker.MagicMock()
    session.execute = mocker.AsyncMock()
    session.commit = mocker.AsyncMock()
    session.rollback = mocker.AsyncMock()
    session.in_transaction = mocker.MagicMock(return_value=True)
    session.get = mocker.AsyncMock()
    session.add = mocker.MagicMock()
    session.flush = mocker.AsyncMock()
    session.refresh = mocker.AsyncMock()

    session.__aenter__ = mocker.AsyncMock(return_value=session)
    session.__aexit__ = mocker.AsyncMock(return_value=None)

    return session


@pytest.fixture
def mock_scalar_result(mocker: MockerFixture):
    result = mocker.MagicMock()
    result.scalar = mocker.MagicMock(return_value=1)
    result.scalars = mocker.MagicMock()
    result.fetchone = mocker.MagicMock()
    result.fetchall = mocker.MagicMock()
    result.rowcount = 1
    return result


# =============================================================================
# Real Database Fixtures (for integration tests)
# =============================================================================

TEST_DB_NAME = "test_data"


@pytest.fixture(scope="session")
def setup_test_database():
    """Session-scoped fixture: creates and initializes the test database once."""
    import asyncio

    from knowgraph.database.database import DatabaseManager
    from knowgraph.database.initdb import init_db

    DatabaseManager.create_db(TEST_DB_NAME)
    asyncio.run(init_db(alter_system=False))


@pytest.fixture
async def clean_tables():
    """Function-scoped fixture: clean all tables between tests.

    Depends on setup_test_database to ensure the database exists.
    """
    from sqlalchemy import delete

    from knowgraph.database.database import DatabaseManager
    from knowgraph.database.tables import ArtifactRawTable, DocumentTable, Source

    db = DatabaseManager(TEST_DB_NAME)
    async with db.asession() as session:
        await session.execute(delete(DocumentTable))
        await session.execute(delete(Source))
        await session.execute(delete(ArtifactRawTable))
        await session.commit()


@pytest.fixture
def real_graph_manager():
    """Provides a real AgeGraphManager connected to the test database."""
    from knowgraph.database.graph import AgeGraphManager

    return AgeGraphManager(dbname=TEST_DB_NAME)


# =============================================================================
# Mock Database Fixtures (for unit tests that don't use real DB)
# =============================================================================


@pytest.fixture
def mock_pool_manager(mocker: MockerFixture):
    """Mock ConnectionPoolManager to prevent real DB connections in unit tests."""
    mock_pool = mocker.MagicMock()
    mock_pool.aengine = mocker.AsyncMock()
    mocker.patch("knowgraph.database.pool.pool_manager", mock_pool)
    mocker.patch("knowgraph.database.database.pool_manager", mock_pool)
    return mock_pool


@pytest.fixture
def mock_graph_manager(mocker: MockerFixture):
    """Creates a mock AgeGraphManager using pytest-mock."""
    mock = mocker.MagicMock()
    mock.afrom_networkx = mocker.AsyncMock(return_value=True)
    mock.atraverse_multi = mocker.AsyncMock(return_value=mocker.MagicMock())
    mock.aget_vertices_by_uris = mocker.AsyncMock(return_value=[])
    mock.aget_all_edge_connections = mocker.AsyncMock(return_value=[])
    mock.aquery_edge_connections_by_entity_names = mocker.AsyncMock(return_value=[])
    return mock


# =============================================================================
# External Service Mocks (always mocked — embedding, tokenizer, LLM, splitter)
# =============================================================================


@pytest.fixture(autouse=True)
def mock_embedding(mocker: MockerFixture) -> Generator:
    """Auto-mock embedding API to prevent network calls."""
    fake_embedding = [[0.1] * 1024]
    mock_embed = mocker.AsyncMock(return_value=fake_embedding)

    mocker.patch("knowgraph.documents.embedder.aembed_documents", mock_embed)
    mocker.patch("knowgraph.database.ragmode.aembed_documents", mock_embed)
    mocker.patch("knowgraph.database.document.aembed_documents", mock_embed)
    yield mock_embed


@pytest.fixture(autouse=True)
def mock_rerank(mocker: MockerFixture) -> Generator:
    """Auto-mock rerank API to prevent network calls."""

    async def _mock_rerank(query: str, documents, topn=None, skip_sorting=False):
        if not documents:
            return []
        for doc in documents:
            if isinstance(doc, Document):
                doc.query_score = 0.85
            else:
                if hasattr(doc, "query_score"):
                    doc.query_score = 0.85
        return list(documents)

    mock_rr = mocker.AsyncMock(side_effect=_mock_rerank)

    mocker.patch("knowgraph.documents.embedder.arerank_documents", mock_rr)
    mocker.patch("knowgraph.database.ragmode.arerank_documents", mock_rr)
    yield mock_rr


@pytest.fixture(autouse=True)
def mock_tokenizer(mocker: MockerFixture) -> Generator:
    """Auto-mock tokenizer to prevent HuggingFace model download."""

    def _mock_tokenize(content: str) -> Counter[int]:
        return Counter({hash(c) % 10000: 1 for c in content if c.strip()})

    mock_tok = mocker.AsyncMock(side_effect=_mock_tokenize)

    mocker.patch("knowgraph.documents.tokenizer.atokenize_content", mock_tok)
    mocker.patch("knowgraph.database.ragmode.atokenize_content", mock_tok)
    mocker.patch("knowgraph.database.document.atokenize_content", mock_tok)
    yield mock_tok


@pytest.fixture(autouse=True)
def mock_splitter(mocker: MockerFixture, sample_chunks: list[str]) -> Generator:
    """Auto-mock splitter to prevent Stanza NLP model download."""

    async def _mock_split(content: str, chunk_size: int = 512, chunk_overlap: int = 32):
        for chunk in sample_chunks:
            yield chunk

    mock_sp = mocker.MagicMock(side_effect=_mock_split)

    mocker.patch("knowgraph.documents.splitter.asplit_content", mock_sp)
    mocker.patch("knowgraph.database.document.asplit_content", mock_sp)
    yield mock_sp


@pytest.fixture(autouse=True)
def mock_llm_extractor(mocker: MockerFixture, sample_entities: list[ExtractedTriple]) -> Generator:
    """Auto-mock LLM extractor to prevent AI model calls."""
    mock_ext = mocker.AsyncMock(return_value=sample_entities)
    mocker.patch("knowgraph.graph.triples.LLMExtractor.aextract_from_document", mock_ext)
    mocker.patch("knowgraph.graph.triples.LLMExtractor.aextract_from_csv_row", mock_ext)
    mocker.patch("knowgraph.graph.triples.LLMExtractor.aextract_from_dataframe", mock_ext)
    yield mock_ext


@pytest.fixture(autouse=True)
def mock_pandas_read_csv(mocker: MockerFixture) -> Generator:
    """Auto-mock pandas read_csv to prevent file I/O."""
    import pandas as pd

    mocker.patch(
        "knowgraph.database.document.pd.read_csv",
        return_value=pd.DataFrame(TEST_CSV_ROWS),
    )
    yield
