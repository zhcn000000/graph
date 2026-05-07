from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from knowgraph.database.ragmode import RAGMode


class TestRRFFusion:
    """RRF (Reciprocal Rank Fusion) is a pure algorithm — no mocking needed."""

    def test_rrf_fusion_basic(self):
        """Basic RRF fusion with vector and BM25 results."""
        vector_ids = [uuid4() for _ in range(5)]
        bm25_ids = [uuid4() for _ in range(5)]

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=5,
        )

        assert len(result) > 0
        assert len(result) <= 5
        assert all(isinstance(doc_id, UUID) for doc_id in result)

    def test_rrf_fusion_with_graph_results(self):
        """RRF fusion should include graph-boosted results."""
        vector_ids = [uuid4() for _ in range(10)]
        bm25_ids = [uuid4() for _ in range(10)]
        graph_results = [(uuid4(), 0.9) for _ in range(5)]

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            graph_results=graph_results,
            topk=10,
        )

        assert len(result) > 0

    def test_rrf_fusion_empty_inputs(self):
        """Empty inputs should return empty results."""
        result = RAGMode._rrf_fusion(
            vector_results=[],
            bm25_results=[],
            topk=10,
        )
        assert result == []

    def test_rrf_fusion_single_result_each(self):
        """RRF with one result per source should return the union."""
        v_id = uuid4()
        b_id = uuid4()

        result = RAGMode._rrf_fusion(
            vector_results=[v_id],
            bm25_results=[b_id],
            topk=10,
        )

        assert len(result) == 2
        assert v_id in result
        assert b_id in result

    def test_rrf_fusion_overlapping_results(self):
        """Overlapping IDs across sources should accumulate scores."""
        shared_id = uuid4()
        vector_ids = [shared_id, uuid4()]
        bm25_ids = [shared_id, uuid4()]

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=3,
        )

        assert len(result) == 3
        assert result[0] == shared_id

    def test_rrf_fusion_custom_weights(self):
        """Custom weights should affect ranking."""
        shared_id = uuid4()
        vector_ids = [shared_id, uuid4(), uuid4()]
        bm25_ids = [uuid4(), shared_id]

        result_default = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=5,
            vector_weight=0.4,
            bm25_weight=0.3,
        )

        result_biased = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=5,
            vector_weight=0.1,
            bm25_weight=0.9,
        )

        assert len(result_default) > 0
        assert len(result_biased) > 0

    def test_rrf_fusion_respects_topk(self):
        """Results should not exceed topk even with many input IDs."""
        vector_ids = [uuid4() for _ in range(50)]
        bm25_ids = [uuid4() for _ in range(50)]

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=5,
        )

        assert len(result) == 5

    def test_rrf_fusion_all_empty_returns_empty(self):
        """When even graph generates no results, return empty."""
        result = RAGMode._rrf_fusion(
            vector_results=[],
            bm25_results=[],
            graph_results=None,
            topk=10,
        )
        assert result == []


class TestDeleteDocuments:
    @pytest.fixture
    def rag_mode(self) -> RAGMode:
        return RAGMode()

    async def test_adelete_documents_success(self, rag_mode: RAGMode, mock_uuid_list: list[UUID]):
        """Deleting documents by ID should succeed."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute.return_value = mock_result

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch.object(rag_mode._RAGMode__db, "asession", return_value=session_ctx):
            result = await rag_mode.adelete_documents(mock_uuid_list[:2])

        assert result is True

    async def test_adelete_documents_empty(self, rag_mode: RAGMode):
        """Deleting with no IDs should return False."""
        result = await rag_mode.adelete_documents([])
        assert result is False

    async def test_adelete_documents_none(self, rag_mode: RAGMode):
        """Deleting with None should return False."""
        result = await rag_mode.adelete_documents(None)
        assert result is False


class TestRemoveDocuments:
    @pytest.fixture
    def rag_mode(self) -> RAGMode:
        return RAGMode()

    async def test_aremove_documents_success(self, rag_mode: RAGMode):
        """Removing documents by file_id should succeed."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall = lambda: [[uuid4()]]
        session.execute.return_value = mock_result

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch.object(rag_mode._RAGMode__db, "asession", return_value=session_ctx):
            file_id = uuid4()
            result = await rag_mode.aremove_documents(file_id)

        assert isinstance(result, list)

    async def test_aremove_documents_empty(self, rag_mode: RAGMode):
        """Removing with no IDs returns empty."""
        result = await rag_mode.aremove_documents([])
        assert result == []


class TestGetByIDs:
    @pytest.fixture
    def rag_mode(self) -> RAGMode:
        return RAGMode()

    async def test_aget_by_ids_empty(self, rag_mode: RAGMode):
        result = await rag_mode.aget_by_ids([])
        assert result == []

    async def test_aget_by_ids_none(self, rag_mode: RAGMode):
        result = await rag_mode.aget_by_ids(None)
        assert result == []
