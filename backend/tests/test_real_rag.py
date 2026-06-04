import os
from pathlib import Path

import pandas as pd
import pytest

from knowgraph.adapters.philamuseum import PhilaMuseumAdapter
from knowgraph.database.artifact import ArtifactStore
from knowgraph.database.document import DocumentStore
from knowgraph.database.ragmode import RAGMode

TEST_DB_NAME = "test_data"
DATA_DIR = Path(__file__).resolve().parent.parent / "doc"

NEEDS_EMBEDDING = bool(os.environ.get("SILICONFLOW_API_KEY"))

INSERT_COUNT = 20
INGEST_COUNT = 10


def _load_artifacts(n: int, *, offset: int = 0) -> list[dict]:
    df = pd.read_csv(DATA_DIR / "clean_artifacts.csv")
    df = df.iloc[offset : offset + n]
    return df.to_dict(orient="records")


@pytest.mark.skipif(not NEEDS_EMBEDDING, reason="SILICONFLOW_API_KEY not set")
@pytest.mark.usefixtures("setup_test_database")
class TestRealDataInsertion:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def rag_mode(self):
        return RAGMode(dbname=TEST_DB_NAME)

    @pytest.fixture
    def artifact_store(self):
        return ArtifactStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def adapter(self):
        return PhilaMuseumAdapter(data_dir=DATA_DIR)

    async def _stage1_insert(self, adapter, artifact_store, n: int = INSERT_COUNT):
        rows = _load_artifacts(n)
        dicts = [adapter.row_to_dict(r) for r in rows if adapter.validate_row(r)]
        assert len(dicts) > 0
        ids = await artifact_store.ainsert_artifacts(dicts)
        assert len(ids) > 0

    async def _stage2_ingest(self, doc_store, n: int = INGEST_COUNT) -> list:
        doc_ids = await doc_store.alingest_artifacts(limit=n)
        assert len(doc_ids) > 0
        return doc_ids

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_vector_search(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, _ = await rag_mode.ahyprid_search(
            queries=["Chinese painting"],
            k=5,
            use_graph=False,
        )
        assert len(results) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_hybrid_search_with_graph(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, graph_entities = await rag_mode.ahyprid_search(
            queries=["Qing Dynasty", "porcelain"],
            k=5,
            use_graph=True,
        )
        assert len(results) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_bm25_search(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, _ = await rag_mode.ahyprid_search(
            queries=["Chinese", "watercolor"],
            k=5,
            use_graph=False,
            vector_weight=0.0,
            bm25_weight=1.0,
        )
        assert len(results) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_get_by_ids(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, _ = await rag_mode.ahyprid_search(
            queries=["Philadelphia"],
            k=1,
            use_graph=False,
        )
        assert len(results) > 0
        doc_id = str(results[0].id)
        fetched = await rag_mode.aget_by_ids([doc_id])
        assert len(fetched) == 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_graph_context(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        context = await rag_mode.aquery_graph_context(
            queries=["Qing Dynasty", "painting"],
            max_hops=2,
        )
        assert "entities" in context
        assert "paths" in context
        assert "relationships" in context

    @pytest.mark.usefixtures("clean_tables")
    async def test_delete_then_search_empty(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        doc_ids = await self._stage2_ingest(doc_store)

        results_before, _ = await rag_mode.ahyprid_search(
            queries=["Philadelphia Museum"],
            k=3,
            use_graph=False,
        )
        assert len(results_before) > 0

        await doc_store.aremove_documents(doc_ids)

        results_after, _ = await rag_mode.ahyprid_search(
            queries=["Philadelphia Museum"],
            k=3,
            use_graph=False,
        )
        assert len(results_after) == 0


@pytest.mark.skipif(not NEEDS_EMBEDDING, reason="SILICONFLOW_API_KEY not set")
@pytest.mark.usefixtures("setup_test_database")
class TestRealDataSearchQuality:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def rag_mode(self):
        return RAGMode(dbname=TEST_DB_NAME)

    @pytest.fixture
    def artifact_store(self):
        return ArtifactStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def adapter(self):
        return PhilaMuseumAdapter(data_dir=DATA_DIR)

    async def _stage1_insert(self, adapter, artifact_store, n: int = INSERT_COUNT):
        rows = _load_artifacts(n)
        dicts = [adapter.row_to_dict(r) for r in rows if adapter.validate_row(r)]
        assert len(dicts) > 0
        ids = await artifact_store.ainsert_artifacts(dicts)
        assert len(ids) > 0

    async def _stage2_ingest(self, doc_store, n: int = INGEST_COUNT) -> list:
        doc_ids = await doc_store.alingest_artifacts(limit=n)
        assert len(doc_ids) > 0
        return doc_ids

    @pytest.mark.usefixtures("clean_tables")
    async def test_relevance_scores_are_valid(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, _ = await rag_mode.ahyprid_search(
            queries=["porcelain", "ceramics"],
            k=10,
            use_graph=False,
        )
        assert len(results) > 0
        for r in results:
            assert r.query_score is not None
            assert 0.0 <= r.query_score <= 1.0

    @pytest.mark.usefixtures("clean_tables")
    async def test_document_context_retrieval(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, _ = await rag_mode.ahyprid_search(
            queries=["painting"],
            k=1,
            use_graph=False,
        )
        assert len(results) > 0
        doc = results[0]
        assert doc.document_index is not None

        context = await rag_mode.aget_document_context(
            document_index=doc.document_index,
        )
        assert context["document_index"] == doc.document_index
        assert len(context["chunks"]) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_document_entities_persisted(self, artifact_store, doc_store, rag_mode, adapter):
        await self._stage1_insert(adapter, artifact_store)
        await self._stage2_ingest(doc_store)

        results, _ = await rag_mode.ahyprid_search(
            queries=["Qing"],
            k=1,
            use_graph=False,
        )
        assert len(results) > 0
        doc = results[0]
        assert doc.document_index is not None

        entities = await rag_mode.aget_document_entities(document_index=doc.document_index)
        assert "document_index" in entities
        assert "entities" in entities
        assert len(entities["entities"]) > 0
