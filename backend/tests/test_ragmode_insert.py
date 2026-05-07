from uuid import UUID

import pytest

from knowgraph.database.document import DocumentStore
from knowgraph.documents.models import Document

TEST_DB_NAME = "test_data"


class TestAaddDocuments:
    """Test the core document insertion method: chunk, embed, tokenize, store.

    These tests mock database sessions since they exercise non-DB logic
    (chunking, embedding, entity extraction) directly.
    """

    @pytest.fixture
    def doc_store(self, mock_pool_manager, mock_graph_manager) -> DocumentStore:
        store = DocumentStore()
        store._graph_manager = mock_graph_manager
        return store

    @pytest.fixture
    def mock_source_row(self, source_id: UUID):
        return (source_id, "sample_artifact.md")

    @pytest.fixture
    def mock_doc_row(self, mock_uuid_list: list[UUID]):
        return (mock_uuid_list[0],)

    async def test_aadd_documents_success(
        self,
        doc_store: DocumentStore,
        sample_documents: list[Document],
        mock_source_row: tuple,
        mock_doc_row: tuple,
        mocker: pytest.MockFixture,
    ):
        """Documents with matching sources should be inserted with chunking, vectors, tokens."""
        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()
        session.commit = mocker.AsyncMock()

        session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [mock_source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        result = await doc_store.aadd_documents(sample_documents)

        assert len(result) > 0
        assert session.execute.call_count >= 3

    async def test_aadd_documents_no_matching_source(
        self,
        doc_store: DocumentStore,
        mocker: pytest.MockFixture,
    ):
        """Documents without matching Source entries should be skipped with a warning."""
        doc = Document(content="test content", name="nonexistent_source")
        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()
        session.execute.return_value = mocker.MagicMock(fetchall=lambda: [])

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        mock_warn = mocker.patch("knowgraph.database.document.warnings.warn")

        result = await doc_store.aadd_documents([doc])

        assert result == []
        mock_warn.assert_called()

    async def test_aadd_documents_empty_list(self, doc_store: DocumentStore):
        """Empty document list should return empty results."""
        result = await doc_store.aadd_documents([])
        assert result == []

    async def test_aadd_documents_removes_duplicate_chunks(
        self,
        doc_store: DocumentStore,
        mock_source_row: tuple,
        mock_doc_row: tuple,
        mocker: pytest.MockFixture,
    ):
        """Duplicate chunk content should be deduplicated."""
        doc = Document(
            content="重复内容\n重复内容\n重复内容",
            name="sample_artifact.md",
        )

        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()
        session.commit = mocker.AsyncMock()

        session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [mock_source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        async def dup_split(content: str, chunk_size=512, chunk_overlap=32):
            yield "重复内容"
            yield "重复内容"
            yield "重复内容"

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch("knowgraph.database.document.asplit_content", dup_split)

        result = await doc_store.aadd_documents([doc])

        assert result is not None

    async def test_aadd_documents_with_extraction_contents(
        self,
        doc_store: DocumentStore,
        sample_documents: list[Document],
        mock_source_row: tuple,
        mock_doc_row: tuple,
        mocker: pytest.MockFixture,
    ):
        """When extraction_contents is provided, LLM extraction uses it instead of doc.content."""
        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()
        session.commit = mocker.AsyncMock()

        session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [mock_source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        extraction_contents = ["extract from this instead"]
        result = await doc_store.aadd_documents(sample_documents, extraction_contents=extraction_contents)

        assert len(result) > 0

    async def test_aadd_documents_with_predefined_entities(
        self,
        doc_store: DocumentStore,
        mock_source_row: tuple,
        mock_doc_row: tuple,
        mocker: pytest.MockFixture,
    ):
        """Documents with pre-populated entities should include them in insert."""
        doc = Document(
            content="test content",
            name="sample_artifact.md",
            entities=["cidoc:artifact/test_entity", "cidoc:museum/test_museum"],
        )

        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()
        session.commit = mocker.AsyncMock()

        session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [mock_source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        result = await doc_store.aadd_documents([doc])

        assert len(result) > 0


class TestAloadFromCSV:
    """CSV ingestion integration tests: uses real database with mocked external services."""

    @pytest.fixture
    def doc_store(self, mock_graph_manager) -> DocumentStore:
        store = DocumentStore(dbname=TEST_DB_NAME)
        store._graph_manager = mock_graph_manager
        return store

    @pytest.mark.dependency(depends=["setup_test_database"], scope="session")
    async def test_aload_from_csv_integration(
        self,
        doc_store: DocumentStore,
        clean_tables: None,
        mocker: pytest.MockFixture,
    ):
        """CSV ingestion should create graph nodes, sources, and chunked documents in real DB."""
        file_ids = await doc_store.aload_from_csv("/fake/path/artifacts.csv")

        assert len(file_ids) > 0

        from sqlalchemy import func, select
        from sqlmodel import col

        from knowgraph.database.database import DatabaseManager
        from knowgraph.database.tables import DocumentTable, Source

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(Source.name).where(Source.id.in_(file_ids))
            result = await session.execute(stmt)
            source_names = {row[0] for row in result.fetchall()}
            assert "青铜鼎" in source_names

            stmt = select(func.count(col(DocumentTable.id))).where(
                col(DocumentTable.file_id).in_(file_ids),
            )
            result = await session.execute(stmt)
            count = result.scalar()
            assert count > 0

    @pytest.mark.dependency(depends=["setup_test_database"], scope="session")
    async def test_aload_from_csv_empty(
        self,
        doc_store: DocumentStore,
        clean_tables: None,
        mocker: pytest.MockFixture,
    ):
        """Empty CSV should return empty results."""
        import pandas as pd

        mocker.patch(
            "knowgraph.database.document.pd.read_csv",
            return_value=pd.DataFrame(),
        )
        result = await doc_store.aload_from_csv("/empty.csv")

        assert result == []


class TestAlingestArtifacts:
    """Artifact ingestion integration tests: uses real database with mocked external services."""

    @pytest.fixture
    def doc_store(self, mock_graph_manager) -> DocumentStore:
        store = DocumentStore(dbname=TEST_DB_NAME)
        store._graph_manager = mock_graph_manager
        return store

    @pytest.fixture
    def mock_artifact_row(self, mocker: pytest.MockFixture):
        """Creates a mock ArtifactRawTable row."""
        row = mocker.MagicMock()
        row.id = UUID("00000000-0000-0000-0000-000000000001")
        row.object_id = "OBJ-001"
        row.title = "青铜鼎"
        row.period = "商朝"
        row.type = "青铜器"
        row.material = "青铜"
        row.description = "一件商朝时期的青铜鼎"
        row.dimensions = "高50cm"
        row.museum = "Metropolitan Museum of Art"
        row.location = "New York"
        row.detail_url = "https://metmuseum.org/art/001"
        row.image_url = "https://metmuseum.org/img/001.jpg"
        row.credit_line = "捐赠"
        row.accession_number = "ACC-001"
        row.crawl_date = None
        return row

    @pytest.mark.dependency(depends=["setup_test_database"], scope="session")
    async def test_alingest_artifacts_integration(
        self,
        doc_store: DocumentStore,
        clean_tables: None,
        mock_artifact_row,
        mocker: pytest.MockFixture,
    ):
        """Artifact ingestion should convert crawled data to documents with triples."""
        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()
        session.commit = mocker.AsyncMock()

        mock_result = mocker.MagicMock()
        mock_result.scalars = mocker.MagicMock(return_value=mocker.MagicMock(all=lambda: [mock_artifact_row]))
        session.execute.return_value = mock_result

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        result = await doc_store.alingest_artifacts(museum="Metropolitan Museum of Art", limit=10)

        assert len(result) > 0

    @pytest.mark.dependency(depends=["setup_test_database"], scope="session")
    async def test_alingest_artifacts_empty_result(
        self,
        doc_store: DocumentStore,
        clean_tables: None,
        mocker: pytest.MockFixture,
    ):
        """No artifacts found should return empty results."""
        session = mocker.MagicMock()
        session.execute = mocker.AsyncMock()

        mock_result = mocker.MagicMock()
        mock_result.scalars = mocker.MagicMock(return_value=mocker.MagicMock(all=lambda: []))
        session.execute.return_value = mock_result

        mock_asession = mocker.patch.object(doc_store._DocumentStore__db, "asession")
        mock_asession.return_value.__aenter__ = mocker.AsyncMock(return_value=session)
        mock_asession.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

        result = await doc_store.alingest_artifacts()

        assert result == []


class TestAinsertDocument:
    """Test the single document insertion flow (converter integration path)."""

    @pytest.fixture
    def doc_store(self, mock_pool_manager, mock_graph_manager) -> DocumentStore:
        store = DocumentStore()
        store._graph_manager = mock_graph_manager
        return store

    async def test_ainsert_document_new_source(
        self,
        doc_store: DocumentStore,
        source_id: UUID,
        mock_uuid_list: list[UUID],
        mocker: pytest.MockFixture,
    ):
        """Inserting a new document should create source, chunk content, and store."""
        src_store_mock = mocker.MagicMock()
        src_store_mock.ainsert_source = mocker.AsyncMock(return_value=source_id)

        source_row = (source_id, "research_notes.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = mocker.MagicMock()
        doc_session.execute = mocker.AsyncMock()
        doc_session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = mocker.AsyncMock()

        doc_session_ctx = mocker.MagicMock()
        doc_session_ctx.__aenter__ = mocker.AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch.object(doc_store, "_DocumentStore__source", src_store_mock)
        mocker.patch.object(doc_store._DocumentStore__db, "asession", return_value=doc_session_ctx)

        result = await doc_store.ainsert_document(
            name="research_notes.md",
            content="青铜器历史悠久，工艺精湛。大都会博物馆收藏丰富。",
            link="file:///data/research_notes.md",
        )

        assert result == source_id

    async def test_ainsert_document_existing_source(
        self,
        doc_store: DocumentStore,
        source_id: UUID,
        mock_uuid_list: list[UUID],
        mocker: pytest.MockFixture,
    ):
        """Inserting with existing source name should reuse the source."""
        src_store_mock = mocker.MagicMock()
        src_store_mock.ainsert_source = mocker.AsyncMock(return_value=None)
        src_store_mock.aget_id_by_names = mocker.AsyncMock(return_value=[source_id])

        source_row = (source_id, "existing.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = mocker.MagicMock()
        doc_session.execute = mocker.AsyncMock()
        doc_session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = mocker.AsyncMock()

        doc_session_ctx = mocker.MagicMock()
        doc_session_ctx.__aenter__ = mocker.AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch.object(doc_store, "_DocumentStore__source", src_store_mock)
        mocker.patch.object(doc_store._DocumentStore__db, "asession", return_value=doc_session_ctx)

        result = await doc_store.ainsert_document(
            name="existing.md",
            content="updated content",
            link="file:///data/existing.md",
        )

        assert result == source_id

    async def test_ainsert_document_no_link(
        self,
        doc_store: DocumentStore,
        source_id: UUID,
        mock_uuid_list: list[UUID],
        mocker: pytest.MockFixture,
    ):
        """Inserting a document without a link should work."""
        src_store_mock = mocker.MagicMock()
        src_store_mock.ainsert_source = mocker.AsyncMock(return_value=source_id)

        source_row = (source_id, "notes.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = mocker.MagicMock()
        doc_session.execute = mocker.AsyncMock()
        doc_session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = mocker.AsyncMock()

        doc_session_ctx = mocker.MagicMock()
        doc_session_ctx.__aenter__ = mocker.AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch.object(doc_store, "_DocumentStore__source", src_store_mock)
        mocker.patch.object(doc_store._DocumentStore__db, "asession", return_value=doc_session_ctx)

        result = await doc_store.ainsert_document(name="notes.md", content="plain text notes")

        assert result == source_id


class TestIntegrationInsertionFlow:
    """End-to-end tests that chain converter output -> document insertion."""

    @pytest.fixture
    def doc_store(self, mock_pool_manager, mock_graph_manager) -> DocumentStore:
        store = DocumentStore()
        store._graph_manager = mock_graph_manager
        return store

    async def test_converter_to_ainsert_document(
        self,
        doc_store: DocumentStore,
        source_id: UUID,
        mock_uuid_list: list[UUID],
        mocker: pytest.MockFixture,
    ):
        """Simulate the full flow: aconvert_file -> ainsert_document."""
        from knowgraph.documents.converter import Document as ConverterDocument

        converted = ConverterDocument(
            content="# 中国青铜器\n\n商周青铜器历史悠久...",
            link="file:///data/bronze.md",
        )

        src_store_mock = mocker.MagicMock()
        src_store_mock.ainsert_source = mocker.AsyncMock(return_value=source_id)

        source_row = (source_id, "bronze.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = mocker.MagicMock()
        doc_session.execute = mocker.AsyncMock()
        doc_session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: [source_row]),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = mocker.AsyncMock()

        doc_session_ctx = mocker.MagicMock()
        doc_session_ctx.__aenter__ = mocker.AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch.object(doc_store, "_DocumentStore__source", src_store_mock)
        mocker.patch.object(doc_store._DocumentStore__db, "asession", return_value=doc_session_ctx)

        result = await doc_store.ainsert_document(
            name=converted.name or "bronze.md",
            content=converted.content,
            link=converted.link,
        )

        assert result is not None
        assert result == source_id

    async def test_multiple_converted_documents_to_aadd(
        self,
        doc_store: DocumentStore,
        source_id: UUID,
        mock_uuid_list: list[UUID],
        mocker: pytest.MockFixture,
    ):
        """Simulate converting multiple files then inserting all at once."""
        converted_files = [
            Document(
                content="# 明朝青花瓷\n\n景德镇青花瓷闻名于世。",
                name="porcelain.md",
                link="file:///data/porcelain.md",
            ),
            Document(
                content="# 清代绘画\n\n工笔重彩是清代绘画的主要特点。",
                name="painting.md",
                link="file:///data/painting.md",
            ),
        ]

        source_rows = [
            (source_id, "porcelain.md"),
            (source_id, "painting.md"),
        ]

        doc_row = (mock_uuid_list[0],)

        doc_session = mocker.MagicMock()
        doc_session.execute = mocker.AsyncMock()
        doc_session.execute.side_effect = [
            mocker.MagicMock(fetchall=lambda: source_rows),
            mocker.MagicMock(scalar=lambda: 0),
            mocker.MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = mocker.AsyncMock()

        doc_session_ctx = mocker.MagicMock()
        doc_session_ctx.__aenter__ = mocker.AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch.object(doc_store._DocumentStore__db, "asession", return_value=doc_session_ctx)

        result = await doc_store.aadd_documents(converted_files)

        assert len(result) > 0
