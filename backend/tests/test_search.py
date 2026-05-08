from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlmodel import col

from knowgraph.database.database import DatabaseManager
from knowgraph.database.document import DocumentStore
from knowgraph.database.ragmode import RAGMode
from knowgraph.database.tables import DocumentTable, Source

TEST_DB_NAME = "test_data"


def make_uuid_list(n: int = 5) -> list[UUID]:
    return [uuid4() for _ in range(n)]


class TestRRFFusion:
    """RRF (Reciprocal Rank Fusion) is a pure algorithm — no DB needed."""

    def test_rrf_fusion_basic(self):
        vector_ids = make_uuid_list(5)
        bm25_ids = make_uuid_list(5)

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=5,
        )

        assert len(result) > 0
        assert len(result) <= 5
        assert all(isinstance(doc_id, UUID) for doc_id in result)

    def test_rrf_fusion_with_graph_results(self):
        vector_ids = make_uuid_list(10)
        bm25_ids = make_uuid_list(10)
        graph_results = [(uuid4(), 0.9) for _ in range(5)]

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            graph_results=graph_results,
            topk=10,
        )

        assert len(result) > 0

    def test_rrf_fusion_empty_inputs(self):
        result = RAGMode._rrf_fusion(vector_results=[], bm25_results=[], topk=10)
        assert result == []

    def test_rrf_fusion_single_result_each(self):
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

    def test_rrf_fusion_respects_topk(self):
        vector_ids = make_uuid_list(50)
        bm25_ids = make_uuid_list(50)

        result = RAGMode._rrf_fusion(
            vector_results=vector_ids,
            bm25_results=bm25_ids,
            topk=5,
        )

        assert len(result) == 5

    def test_rrf_fusion_all_empty_returns_empty(self):
        result = RAGMode._rrf_fusion(
            vector_results=[],
            bm25_results=[],
            graph_results=None,
            topk=10,
        )
        assert result == []


ARTIFACT_SEARCH_CONTENT = (
    "中国古代青铜器历史悠久。商周时期的青铜器制作工艺精湛，造型优美。"
    "饕餮纹和云雷纹是青铜器上常见的纹饰。"
    "大都会博物馆收藏了大量中国青铜器，其中以商代青铜鼎最为著名。"
)

PORCELAIN_SEARCH_CONTENT = (
    "景德镇青花瓷闻名于世。明朝青花瓷工艺达到顶峰，蓝色釉料独特。"
    "元代青花瓷使用进口钴料，发色浓郁。清代青花瓷色彩更加丰富多变。"
)

PAINTING_SEARCH_CONTENT = (
    "清代宫廷绘画以工笔重彩为主。题材包括山水、人物、花鸟。北京故宫博物院收藏了大量清代宫廷绘画精品。"
)


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestInsertAndSearch:
    """Insert real documents then search using real embedding + reranking APIs."""

    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def rag_mode(self):
        return RAGMode(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_vector_search(self, doc_store, rag_mode):
        """Insert a document and verify vector search finds it."""
        source_id = await doc_store.ainsert_document(
            name="bronze_art.md",
            content=ARTIFACT_SEARCH_CONTENT,
        )
        assert source_id is not None

        results, _ = await rag_mode.ahyprid_search(
            queries=["中国青铜器 古代 纹饰"],
            k=3,
        )

        assert len(results) > 0
        contents = [r.content for r in results]
        assert any("青铜器" in c for c in contents)

    @pytest.mark.usefixtures("clean_tables")
    async def test_insert_then_hybrid_search(self, doc_store, rag_mode):
        """Multiple documents should be findable by hybrid search."""
        await doc_store.ainsert_document(
            name="porcelain.md",
            content=PORCELAIN_SEARCH_CONTENT,
        )
        await doc_store.ainsert_document(
            name="painting.md",
            content=PAINTING_SEARCH_CONTENT,
        )

        results, _ = await rag_mode.ahyprid_search(
            queries=["青花瓷 景德镇"],
            k=3,
        )

        assert len(results) > 0
        contents = [r.content for r in results]
        assert any("青花瓷" in c or "景德镇" in c for c in contents)

    @pytest.mark.usefixtures("clean_tables")
    async def test_search_empty_db(self, rag_mode):
        """Search against empty database returns empty results."""
        results, graph_entities = await rag_mode.ahyprid_search(
            queries=["nothing"],
            k=3,
        )
        assert results == []
        assert graph_entities == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_documents(self, doc_store, rag_mode):
        """aquery_documents should return structured search results."""
        await doc_store.ainsert_document(
            name="bronze_ritual.md",
            content="商代青铜鼎高50cm，用于祭祀仪式。饕餮纹是其标志性纹饰。西周青铜器铭文记载了大量历史事件。",
        )

        results = await rag_mode.aquery_documents(
            queries=["青铜鼎 商代 祭祀"],
        )

        assert len(results) > 0
        for r in results:
            assert isinstance(r.content, str)
            assert r.score >= 0.0

    @pytest.mark.usefixtures("clean_tables")
    async def test_search_with_graph(self, doc_store, rag_mode):
        """Search with graph boosting enabled should work."""
        await doc_store.ainsert_document(
            name="museum_collection.md",
            content=ARTIFACT_SEARCH_CONTENT,
        )

        results, graph_entities = await rag_mode.ahyprid_search(
            queries=["大都会博物馆 青铜器"],
            k=3,
            use_graph=True,
        )

        assert len(results) > 0


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestGetAndDelete:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def rag_mode(self):
        return RAGMode(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_by_ids(self, doc_store, rag_mode):
        """aget_by_ids should return documents for given IDs."""
        source_id = await doc_store.ainsert_document(
            name="get_by_id_test.md",
            content="测试获取文档内容。青铜鼎是商代重要祭祀礼器。",
        )
        assert source_id is not None

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = (
                select(col(DocumentTable.id))
                .where(
                    col(DocumentTable.file_id) == source_id,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            doc_id = result.scalar_one()
            doc_id_str = str(doc_id)

        documents = await rag_mode.aget_by_ids([doc_id_str])
        assert len(documents) == 1
        assert "青铜鼎" in documents[0].content

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_by_ids_empty(self, rag_mode):
        result = await rag_mode.aget_by_ids([])
        assert result == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_by_ids_none(self, rag_mode):
        result = await rag_mode.aget_by_ids(None)
        assert result == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_documents_success(self, doc_store):
        """Delete documents by ID and verify removal."""
        source_id = await doc_store.ainsert_document(
            name="delete_test.md",
            content="待删除的文档内容。青花瓷是景德镇的代表性瓷器。",
        )
        assert source_id is not None

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable.id)).where(
                col(DocumentTable.file_id) == source_id,
            )
            result = await session.execute(stmt)
            doc_ids = [row[0] for row in result.fetchall()]
        assert len(doc_ids) > 0

        result = await doc_store.adelete_documents(doc_ids)
        assert result is True

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            cnt_stmt = select(func.count(col(DocumentTable.id))).where(
                col(DocumentTable.id).in_(doc_ids),
            )
            result = await session.execute(cnt_stmt)
            assert result.scalar() == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_documents_empty(self, doc_store):
        result = await doc_store.adelete_documents([])
        assert result is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_documents_none(self, doc_store):
        result = await doc_store.adelete_documents(None)
        assert result is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_aremove_documents_success(self, doc_store):
        """Remove documents by file_id."""
        source_id = await doc_store.ainsert_document(
            name="remove_test.md",
            content="待移除的文档内容。清代绘画以山水花鸟为主题。",
        )
        assert source_id is not None

        result = await doc_store.aremove_documents(source_id)
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_aremove_documents_empty(self, doc_store):
        result = await doc_store.aremove_documents([])
        assert result == []


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestGraphContext:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.fixture
    def rag_mode(self):
        return RAGMode(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_graph_context(self, doc_store, rag_mode):
        """Graph context query should return entities/paths/relationships."""
        await doc_store.ainsert_document(
            name="graph_context.md",
            content="大都会博物馆收藏的商代青铜鼎是重要文物。青铜鼎是青铜器的典型代表，纹饰精美。",
        )

        context = await rag_mode.aquery_graph_context(
            queries=["大都会博物馆 青铜鼎"],
            max_hops=2,
        )

        assert "entities" in context
        assert "paths" in context
        assert "relationships" in context

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_document_context(self, doc_store, rag_mode):
        """aget_document_context should return chunks with surrounding context."""
        await doc_store.ainsert_document(
            name="doc_context.md",
            content="中国青铜器历史悠久。商周青铜器工艺精湛。大都会博物馆收藏丰富。"
            "清代绘画以工笔重彩为主。北京故宫博物院收藏了大量清代绘画精品。",
        )

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = (
                select(col(DocumentTable.document_index))
                .where(
                    col(Source.name) == "doc_context.md",
                )
                .join(Source, col(Source.id) == col(DocumentTable.file_id))
                .limit(1)
            )
            result = await session.execute(stmt)
            doc_index = result.scalar_one()

        context = await rag_mode.aget_document_context(
            document_index=doc_index,
            chunk_index=0,
            before=1,
            after=1,
        )

        assert context["document_index"] == doc_index
        assert len(context["chunks"]) > 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_document_entities(self, doc_store, rag_mode):
        """aget_document_entities should return entities associated with document."""
        await doc_store.ainsert_document(
            name="entities_context.md",
            content="景德镇青花瓷工艺精湛。大都会博物馆收藏了大量中国瓷器。青花瓷以其蓝色釉料闻名于世。",
        )

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = (
                select(col(DocumentTable.document_index))
                .where(
                    col(Source.name) == "entities_context.md",
                )
                .join(Source, col(Source.id) == col(DocumentTable.file_id))
                .limit(1)
            )
            result = await session.execute(stmt)
            doc_index = result.scalar_one()

        entities = await rag_mode.aget_document_entities(document_index=doc_index)

        assert "document_index" in entities
        assert "entities" in entities
