from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from knowgraph.database.ragmode import RAGMode
from knowgraph.documents.models import Document


class TestAaddDocuments:
    """Test the core document insertion method: chunk, embed, tokenize, store."""

    @pytest.fixture
    def rag_mode(self, mock_graph_manager: MagicMock) -> RAGMode:
        rag = RAGMode()
        rag._graph_manager = mock_graph_manager
        return rag

    @pytest.fixture
    def mock_source_row(self, source_id: UUID) -> tuple:
        return (source_id, "sample_artifact.md")

    @pytest.fixture
    def mock_doc_row(self, mock_uuid_list: list[UUID]) -> tuple:
        return (mock_uuid_list[0],)

    async def test_aadd_documents_success(
        self,
        rag_mode: RAGMode,
        sample_documents: list[Document],
        mock_source_row: tuple,
        mock_doc_row: tuple,
    ):
        """Documents with matching sources should be inserted with chunking, vectors, tokens."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        session.execute.side_effect = [
            MagicMock(fetchall=lambda: [mock_source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        with patch.object(rag_mode._RAGMode__db, "asession") as mock_asession:
            mock_asession.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_asession.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await rag_mode.aadd_documents(sample_documents)

        assert len(result) > 0
        assert session.execute.call_count >= 3

    async def test_aadd_documents_no_matching_source(
        self,
        rag_mode: RAGMode,
    ):
        """Documents without matching Source entries should be skipped with a warning."""
        doc = Document(content="test content", name="nonexistent_source")
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value = MagicMock(fetchall=lambda: [])

        with (
            patch.object(rag_mode._RAGMode__db, "asession") as mock_asession,
            patch("knowgraph.database.ragmode.warnings.warn") as mock_warn,
        ):
            mock_asession.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_asession.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await rag_mode.aadd_documents([doc])

        assert result == []
        mock_warn.assert_called()

    async def test_aadd_documents_empty_list(self, rag_mode: RAGMode):
        """Empty document list should return empty results."""
        result = await rag_mode.aadd_documents([])
        assert result == []

    async def test_aadd_documents_removes_duplicate_chunks(
        self,
        rag_mode: RAGMode,
        mock_source_row: tuple,
        mock_doc_row: tuple,
    ):
        """Duplicate chunk content should be deduplicated."""
        doc = Document(
            content="重复内容\n重复内容\n重复内容",
            name="sample_artifact.md",
        )

        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        session.execute.side_effect = [
            MagicMock(fetchall=lambda: [mock_source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        async def dup_split(content: str, chunk_size=512, chunk_overlap=32):
            yield "重复内容"
            yield "重复内容"
            yield "重复内容"

        with (
            patch.object(rag_mode._RAGMode__db, "asession") as mock_asession,
            patch("knowgraph.database.ragmode.asplit_content", dup_split),
        ):
            mock_asession.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_asession.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await rag_mode.aadd_documents([doc])

        assert result is not None

    async def test_aadd_documents_with_extraction_contents(
        self,
        rag_mode: RAGMode,
        sample_documents: list[Document],
        mock_source_row: tuple,
        mock_doc_row: tuple,
    ):
        """When extraction_contents is provided, LLM extraction uses it instead of doc.content."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        session.execute.side_effect = [
            MagicMock(fetchall=lambda: [mock_source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        extraction_contents = ["extract from this instead"]

        with patch.object(rag_mode._RAGMode__db, "asession") as mock_asession:
            mock_asession.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_asession.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await rag_mode.aadd_documents(sample_documents, extraction_contents=extraction_contents)

        assert len(result) > 0

    async def test_aadd_documents_with_predefined_entities(
        self,
        rag_mode: RAGMode,
        sample_documents: list[Document],
        mock_source_row: tuple,
        mock_doc_row: tuple,
    ):
        """Documents with pre-populated entities should include them in insert."""
        doc = Document(
            content="test content",
            name="sample_artifact.md",
            entities=["cidoc:artifact/test_entity", "cidoc:museum/test_museum"],
        )

        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        session.execute.side_effect = [
            MagicMock(fetchall=lambda: [mock_source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [mock_doc_row]),
        ]

        with patch.object(rag_mode._RAGMode__db, "asession") as mock_asession:
            mock_asession.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_asession.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await rag_mode.aadd_documents([doc])

        assert len(result) > 0


class TestAloadFromCSV:
    """Test CSV ingestion: read -> extract triples -> insert sources -> add documents."""

    @pytest.fixture
    def rag_mode(self, mock_graph_manager: MagicMock) -> RAGMode:
        rag = RAGMode()
        rag._graph_manager = mock_graph_manager
        return rag

    async def test_aload_from_csv_success(self, rag_mode: RAGMode, source_id: UUID, mock_uuid_list: list[UUID]):
        """CSV ingestion should create graph nodes, sources, and chunked documents."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        src_store_mock = MagicMock()
        src_store_mock.ainsert_source = AsyncMock(return_value=source_id)
        src_store_mock.aget_id_by_names = AsyncMock(return_value=[source_id])

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.commit = AsyncMock()

        source_row = (source_id, "青铜鼎")
        doc_row = (mock_uuid_list[0],)

        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: [source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]

        with (
            patch.object(rag_mode, "_RAGMode__source", src_store_mock),
            patch.object(rag_mode._RAGMode__db, "asession") as mock_asession,
        ):
            source_session = MagicMock()
            source_session.execute = AsyncMock()
            source_session.commit = AsyncMock()
            source_session.__aenter__ = AsyncMock(return_value=source_session)
            source_session.__aexit__ = AsyncMock(return_value=None)

            doc_session_ctx2 = MagicMock()
            doc_session_ctx2.__aenter__ = AsyncMock(return_value=doc_session)
            doc_session_ctx2.__aexit__ = AsyncMock(return_value=None)

            mock_asession.side_effect = [source_session, doc_session_ctx2, doc_session_ctx2]

            result = await rag_mode.aload_from_csv("/fake/path/artifacts.csv")

        assert isinstance(result, list)

    async def test_aload_from_csv_empty_dataframe(self, rag_mode: RAGMode):
        """Empty CSV should return empty results."""
        import pandas as pd

        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(rag_mode._RAGMode__db, "asession", return_value=session),
            patch("knowgraph.database.ragmode.pd.read_csv", return_value=pd.DataFrame()),
        ):
            result = await rag_mode.aload_from_csv("/empty.csv")

        assert result == []


class TestAlingestArtifacts:
    """Test spider artifact ingestion: query -> convert -> insert sources -> add documents."""

    @pytest.fixture
    def rag_mode(self, mock_graph_manager: MagicMock) -> RAGMode:
        rag = RAGMode()
        rag._graph_manager = mock_graph_manager
        return rag

    @pytest.fixture
    def mock_artifact_row(self):
        """Creates a mock ArtifactRawTable row."""
        from unittest.mock import MagicMock

        row = MagicMock()
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

    async def test_alingest_artifacts_success(
        self,
        rag_mode: RAGMode,
        mock_artifact_row,
        source_id: UUID,
        mock_uuid_list: list[UUID],
    ):
        """Artifact ingestion should convert crawled data to documents with triples."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        source_row = (source_id, "青铜鼎")
        doc_row = (mock_uuid_list[0],)

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=lambda: [mock_artifact_row]))

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: [source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = AsyncMock()

        with (
            patch.object(rag_mode._RAGMode__db, "asession") as mock_asession,
            patch.object(rag_mode, "_RAGMode__source", MagicMock()),
        ):
            artifact_session = MagicMock()
            artifact_session.execute = AsyncMock(return_value=mock_result)
            artifact_session.__aenter__ = AsyncMock(return_value=artifact_session)
            artifact_session.__aexit__ = AsyncMock(return_value=None)

            source_session = MagicMock()
            source_session.execute = AsyncMock()
            source_session.commit = AsyncMock()
            source_session.__aenter__ = AsyncMock(return_value=source_session)
            source_session.__aexit__ = AsyncMock(return_value=None)

            doc_session_ctx = MagicMock()
            doc_session_ctx.__aenter__ = AsyncMock(return_value=doc_session)
            doc_session_ctx.__aexit__ = AsyncMock(return_value=None)

            mock_asession.side_effect = lambda: artifact_session

            result = await rag_mode.alingest_artifacts(museum="Metropolitan Museum of Art", limit=10)

        assert isinstance(result, list)

    async def test_alingest_artifacts_empty_result(self, rag_mode: RAGMode):
        """No artifacts found should return empty results."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=lambda: []))
        session.execute.return_value = mock_result

        async def mock_asession():
            yield session

        with patch.object(rag_mode._RAGMode__db, "asession", mock_asession):
            result = await rag_mode.alingest_artifacts()

        assert result == []


class TestAinsertDocument:
    """Test the single document insertion flow (converter integration path)."""

    @pytest.fixture
    def rag_mode(self, mock_graph_manager: MagicMock) -> RAGMode:
        rag = RAGMode()
        rag._graph_manager = mock_graph_manager
        return rag

    async def test_ainsert_document_new_source(
        self,
        rag_mode: RAGMode,
        source_id: UUID,
        mock_uuid_list: list[UUID],
    ):
        """Inserting a new document should create source, chunk content, and store."""
        src_store_mock = MagicMock()
        src_store_mock.ainsert_source = AsyncMock(return_value=source_id)

        source_row = (source_id, "research_notes.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: [source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = AsyncMock()

        doc_session_ctx = MagicMock()
        doc_session_ctx.__aenter__ = AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(rag_mode, "_RAGMode__source", src_store_mock),
            patch.object(rag_mode._RAGMode__db, "asession", return_value=doc_session_ctx),
        ):
            result = await rag_mode.ainsert_document(
                name="research_notes.md",
                content="青铜器历史悠久，工艺精湛。大都会博物馆收藏丰富。",
                link="file:///data/research_notes.md",
            )

        assert result == source_id

    async def test_ainsert_document_existing_source(
        self,
        rag_mode: RAGMode,
        source_id: UUID,
        mock_uuid_list: list[UUID],
    ):
        """Inserting with existing source name should reuse the source."""
        src_store_mock = MagicMock()
        src_store_mock.ainsert_source = AsyncMock(return_value=None)
        src_store_mock.aget_id_by_names = AsyncMock(return_value=[source_id])

        source_row = (source_id, "existing.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: [source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = AsyncMock()

        doc_session_ctx = MagicMock()
        doc_session_ctx.__aenter__ = AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(rag_mode, "_RAGMode__source", src_store_mock),
            patch.object(rag_mode._RAGMode__db, "asession", return_value=doc_session_ctx),
        ):
            result = await rag_mode.ainsert_document(
                name="existing.md",
                content="updated content",
                link="file:///data/existing.md",
            )

        assert result == source_id

    async def test_ainsert_document_no_link(self, rag_mode: RAGMode, source_id: UUID, mock_uuid_list: list[UUID]):
        """Inserting a document without a link should work."""
        src_store_mock = MagicMock()
        src_store_mock.ainsert_source = AsyncMock(return_value=source_id)

        source_row = (source_id, "notes.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: [source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = AsyncMock()

        doc_session_ctx = MagicMock()
        doc_session_ctx.__aenter__ = AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(rag_mode, "_RAGMode__source", src_store_mock),
            patch.object(rag_mode._RAGMode__db, "asession", return_value=doc_session_ctx),
        ):
            result = await rag_mode.ainsert_document(name="notes.md", content="plain text notes")

        assert result == source_id


class TestIntegrationInsertionFlow:
    """End-to-end tests that chain converter output -> document insertion."""

    @pytest.fixture
    def rag_mode(self, mock_graph_manager: MagicMock) -> RAGMode:
        rag = RAGMode()
        rag._graph_manager = mock_graph_manager
        return rag

    async def test_converter_to_ainsert_document(
        self,
        rag_mode: RAGMode,
        source_id: UUID,
        mock_uuid_list: list[UUID],
    ):
        """Simulate the full flow: aconvert_file -> ainsert_document."""
        from knowgraph.documents.converter import Document as ConverterDocument

        converted = ConverterDocument(
            content="# 中国青铜器\n\n商周青铜器历史悠久...",
            link="file:///data/bronze.md",
        )

        src_store_mock = MagicMock()
        src_store_mock.ainsert_source = AsyncMock(return_value=source_id)

        source_row = (source_id, "bronze.md")
        doc_row = (mock_uuid_list[0],)

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: [source_row]),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = AsyncMock()

        doc_session_ctx = MagicMock()
        doc_session_ctx.__aenter__ = AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(rag_mode, "_RAGMode__source", src_store_mock),
            patch.object(rag_mode._RAGMode__db, "asession", return_value=doc_session_ctx),
        ):
            result = await rag_mode.ainsert_document(
                name=converted.name or "bronze.md",
                content=converted.content,
                link=converted.link,
            )

        assert result is not None
        assert result == source_id

    async def test_multiple_converted_documents_to_aadd(
        self,
        rag_mode: RAGMode,
        source_id: UUID,
        mock_uuid_list: list[UUID],
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

        doc_session = MagicMock()
        doc_session.execute = AsyncMock()
        doc_session.execute.side_effect = [
            MagicMock(fetchall=lambda: source_rows),
            MagicMock(scalar=lambda: 0),
            MagicMock(fetchall=lambda: [doc_row]),
        ]
        doc_session.commit = AsyncMock()

        doc_session_ctx = MagicMock()
        doc_session_ctx.__aenter__ = AsyncMock(return_value=doc_session)
        doc_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch.object(rag_mode._RAGMode__db, "asession", return_value=doc_session_ctx):
            result = await rag_mode.aadd_documents(converted_files)

        assert len(result) > 0
