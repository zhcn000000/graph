import pytest
from sqlalchemy import func, select
from sqlmodel import col

from knowgraph.database.database import DatabaseManager
from knowgraph.database.document import DocumentStore
from knowgraph.database.source import SourceStore
from knowgraph.database.tables import DocumentTable, Source
from knowgraph.documents.models import Document
from knowgraph.graph.schema import ExtractedTriple

TEST_DB_NAME = "test_data"


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
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
        doc = Document(
            content="商代青铜器是重要的考古发现。饕餮纹和云雷纹是常见纹饰。",
            name="nonexistent_source.md",
        )
        result = await doc_store.aadd_documents([doc])
        assert result == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_with_predefined_entities(
        self,
        doc_store,
        sample_documents: list[Document],
        sample_entities: list[ExtractedTriple],
    ):
        """Documents with pre-populated entities should store them."""
        doc_name = sample_documents[0].name
        assert doc_name is not None

        source_store = SourceStore(dbname=TEST_DB_NAME)
        source_id = await source_store.ainsert_source(name=doc_name)
        assert source_id is not None

        doc = Document(
            content=sample_documents[0].content,
            name=doc_name,
            triples=sample_entities[:2],
            file_id=source_id,
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
            assert "cidoc:artifact/青铜鼎" in all_entities


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestIntegrationFlow:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_multiple_documents_inserted_together(
        self, doc_store, sample_documents: list[Document], sample_entities: list[ExtractedTriple]
    ):
        """Insert multiple documents via aadd_documents with pre-created sources."""
        source_store = SourceStore(dbname=TEST_DB_NAME)
        source_ids = []
        for doc in sample_documents:
            assert doc.name is not None
            source_id = await source_store.ainsert_source(name=doc.name)
            source_ids.append(source_id)

        name_a = sample_documents[0].name
        name_b = sample_documents[1].name
        assert name_a is not None
        assert name_b is not None

        docs = [
            Document(
                content=sample_documents[0].content,
                name=name_a,
                triples=sample_entities[:2],
                file_id=source_ids[0],
            ),
            Document(
                content=sample_documents[1].content,
                name=name_b,
                triples=sample_entities[2:],
                file_id=source_ids[1],
            ),
        ]

        result = await doc_store.aadd_documents(docs)
        assert len(result) > 0

        db = DatabaseManager(TEST_DB_NAME)
        source_names = [name_a, name_b]
        async with db.asession() as session:
            cnt_stmt = select(func.count(col(DocumentTable.id))).where(
                col(DocumentTable.file_id).in_(
                    select(col(Source.id)).where(col(Source.name).in_(source_names)),
                ),
            )
            result = await session.execute(cnt_stmt)
            assert (result.scalar() or 0) >= 2
