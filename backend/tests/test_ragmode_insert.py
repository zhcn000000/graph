import pytest
from sqlalchemy import func, select
from sqlmodel import col

from knowgraph.database.database import DatabaseManager
from knowgraph.database.document import DocumentStore
from knowgraph.database.source import SourceStore
from knowgraph.database.tables import DocumentTable, Source
from knowgraph.documents.models import Document

TEST_DB_NAME = "test_data"

pytestmark = pytest.mark.real_services


@pytest.mark.usefixtures("setup_test_database")
class TestAinsertDocument:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_ainsert_document_creates_source_and_chunks(self, doc_store):
        """Insert with real DB, embedding, splitter, tokenizer."""
        source_id = await doc_store.ainsert_document(
            name="test_insert.md",
            content="中国古代青铜器历史悠久工艺精湛。商周时期的青铜器制作工艺达到顶峰。"
            "大都会博物馆收藏了大量中国青铜器。",
        )
        assert source_id is not None

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            src_stmt = select(col(Source.id), col(Source.name)).where(
                col(Source.name) == "test_insert.md",
            )
            result = await session.execute(src_stmt)
            assert result.fetchone() is not None

            cnt_stmt = select(func.count(col(DocumentTable.id))).where(
                col(DocumentTable.file_id) == source_id,
            )
            result = await session.execute(cnt_stmt)
            assert result.scalar() > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_ainsert_document_with_link(self, doc_store):
        """Insert with link should store the link in Source."""
        source_id = await doc_store.ainsert_document(
            name="linked_doc.md",
            content="明朝青花瓷以其独特的蓝色釉料闻名于世。",
            link="https://example.com/linked.md",
        )
        assert source_id is not None

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            src_stmt = select(col(Source.link)).where(col(Source.id) == source_id)
            result = await session.execute(src_stmt)
            assert result.scalar_one() == "https://example.com/linked.md"

    @pytest.mark.usefixtures("clean_tables")
    async def test_ainsert_document_stores_vectors_and_tokens(self, doc_store):
        """Insert document and verify vectors/tokens are non-empty."""
        source_id = await doc_store.ainsert_document(
            name="vectors_test.md",
            content="景德镇是青花瓷的主要产地。清代绘画以工笔重彩为主。",
        )
        assert source_id is not None

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable)).where(
                col(DocumentTable.file_id) == source_id,
            )
            result = await session.execute(stmt)
            rows = result.fetchall()
            assert len(rows) > 0
            for row in rows:
                doc_row = row[0]
                assert doc_row.vector is not None and len(doc_row.vector) > 0
                assert doc_row.bmvector is not None and len(doc_row.bmvector) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_ainsert_document_existing_source(self, doc_store):
        """Re-inserting with same name reuses source."""
        source_id_1 = await doc_store.ainsert_document(
            name="reuse_source.md",
            content="商代青铜鼎是重要的祭祀器物。",
        )
        assert source_id_1 is not None

        source_id_2 = await doc_store.ainsert_document(
            name="reuse_source.md",
            content="补充说明：青铜鼎纹饰丰富多样。",
        )
        assert source_id_2 == source_id_1

    @pytest.mark.usefixtures("clean_tables")
    async def test_ainsert_document_argument_kinds(self, doc_store):
        """Insert without link should work."""
        source_id = await doc_store.ainsert_document(
            name="nolink.md",
            content="plain text notes",
        )
        assert source_id is not None


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
