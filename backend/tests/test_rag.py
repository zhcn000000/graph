import pytest
from sqlalchemy import func, select
from sqlmodel import col

from knowgraph.database.database import DatabaseManager
from knowgraph.database.document import DocumentStore
from knowgraph.database.source import SourceStore
from knowgraph.database.tables import DocumentTable, Source
from knowgraph.documents.models import Document

TEST_DB_NAME = "test_data"


@pytest.mark.usefixtures("setup_test_database")
class TestAaddDocuments:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_empty_list(self, doc_store):
        result = await doc_store.aadd_documents([])
        assert result == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_no_matching_source(self, doc_store):
        """Document without matching Source should be skipped."""
        doc = Document(content="test content", name="nonexistent_source")
        result = await doc_store.aadd_documents([doc])
        assert result == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_with_predefined_entities(self, doc_store):
        """Documents with pre-populated entities should store them."""
        source_store = SourceStore(dbname=TEST_DB_NAME)
        source_id = await source_store.ainsert_source(name="entities_test.md")
        assert source_id is not None

        doc = Document(
            content="商代青铜鼎是重要的祭祀器物。",
            name="entities_test.md",
            entities=["cidoc:artifact/custom_entity"],
        )
        result = await doc_store.aadd_documents([doc])
        assert len(result) > 0

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable.entities)).where(
                col(DocumentTable.file_id) == source_id,
            )
            result = await session.execute(stmt)
            all_entities: set[str] = set()
            for row in result.fetchall():
                if row[0]:
                    all_entities.update(row[0])
            assert "cidoc:artifact/custom_entity" in all_entities


@pytest.mark.usefixtures("setup_test_database")
class TestIntegrationFlow:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_multiple_documents_inserted_together(self, doc_store):
        """Insert multiple documents via aadd_documents with pre-created sources."""
        source_store = SourceStore(dbname=TEST_DB_NAME)
        for name in ("doc_a.md", "doc_b.md"):
            await source_store.ainsert_source(name=name)

        docs = [
            Document(
                content="青铜器是中国古代文明的瑰宝。",
                name="doc_a.md",
            ),
            Document(
                content="青花瓷以其独特的蓝色釉料闻名于世。",
                name="doc_b.md",
            ),
        ]

        result = await doc_store.aadd_documents(docs)
        assert len(result) > 0

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            cnt_stmt = select(func.count(col(DocumentTable.id))).where(
                col(DocumentTable.file_id).in_(
                    select(col(Source.id)).where(col(Source.name).in_(["doc_a.md", "doc_b.md"])),
                ),
            )
            result = await session.execute(cnt_stmt)
            assert result.scalar() >= 2
