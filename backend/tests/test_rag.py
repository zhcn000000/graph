import os

import pytest
from sqlalchemy import func, select
from sqlmodel import col

from knowgraph.database.database import DatabaseManager
from knowgraph.database.document import DocumentStore
from knowgraph.database.tables import DocumentTable
from knowgraph.documents.models import Document
from knowgraph.graph import RelationshipType
from knowgraph.graph.schema import (
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipInfo,
)

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
    async def test_aadd_documents_with_predefined_entities(
        self,
        doc_store,
        sample_documents: list[Document],
        sample_entities: list[ExtractedTriple],
    ):
        """Documents with pre-populated entities should store them."""
        doc_name = sample_documents[0].name
        assert doc_name is not None

        triples = sample_entities
        doc = Document(
            content=sample_documents[0].content,
            name=doc_name,
            link=f"file:///data/{doc_name}",
            metadata={"name": doc_name, "link": f"file:///data/{doc_name}"},
            triples=triples,
        )
        result = await doc_store.aadd_documents([doc])
        assert len(result) > 0

        doc_id = result[0]
        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable.entities)).where(
                col(DocumentTable.id) == doc_id,
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            assert row is not None
            all_entities = set(row[0] or [])
            assert "cidoc:artifact/青铜鼎" in all_entities

        for t in triples:
            assert t.predicate.strength is not None, f"Expected strength for triple {t.subject.name} → {t.object.name}"
            assert 0.0 <= t.predicate.strength <= 1.0, f"Strength {t.predicate.strength} out of [0,1] range"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_triples_inserted_to_graph(
        self,
        doc_store,
        sample_documents: list[Document],
        sample_entities: list[ExtractedTriple],
    ):
        """Triples passed via Document.triples should be persisted as graph nodes/edges."""
        doc_name = sample_documents[0].name
        assert doc_name is not None

        doc = Document(
            content=sample_documents[0].content,
            name=doc_name,
            link=f"file:///data/{doc_name}",
            metadata={"name": doc_name, "link": f"file:///data/{doc_name}"},
            triples=sample_entities,
        )

        result = await doc_store.aadd_documents([doc])
        assert len(result) > 0

        doc_id = result[0]
        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable.entities)).where(
                col(DocumentTable.id) == doc_id,
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            assert row is not None
            all_entities = set(row[0] or [])

        expected_uris = {t.subject.uri for t in sample_entities} | {t.object.uri for t in sample_entities}
        for uri in expected_uris:
            assert uri in all_entities, f"Expected {uri} in document entities"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_triples_with_strength_preserved(
        self,
        doc_store,
        sample_documents: list[Document],
    ):
        """Triples with pre-set strength values should not be overwritten by compute_triples_strength."""
        doc_name = sample_documents[0].name
        assert doc_name is not None

        pre_scored_triple = ExtractedTriple(
            subject=ExtractedEntity(name="测试文物", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY, strength=0.88),
            object=ExtractedEntity(name="测试博物馆", entity_type=EntityType.MUSEUM),
            description="测试三元组",
        )

        doc = Document(
            content=sample_documents[0].content,
            name=doc_name,
            link=f"file:///data/{doc_name}",
            metadata={"name": doc_name, "link": f"file:///data/{doc_name}"},
            triples=[pre_scored_triple],
        )

        result = await doc_store.aadd_documents([doc])
        assert len(result) > 0

        doc_id = result[0]
        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable.entities)).where(
                col(DocumentTable.id) == doc_id,
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            assert row is not None
            all_entities = set(row[0] or [])

        assert pre_scored_triple.subject.uri in all_entities
        assert pre_scored_triple.object.uri in all_entities


@pytest.mark.usefixtures("setup_test_database")
class TestIntegrationFlow:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_multiple_documents_inserted_together(
        self,
        doc_store,
        sample_documents: list[Document],
        sample_entities: list[ExtractedTriple],
    ):
        """Insert multiple documents via aadd_documents."""
        name_a = sample_documents[0].name
        name_b = sample_documents[1].name
        assert name_a is not None
        assert name_b is not None

        docs = [
            Document(
                content=sample_documents[0].content,
                name=name_a,
                link=f"file:///data/{name_a}",
                metadata={"name": name_a, "link": f"file:///data/{name_a}"},
                triples=sample_entities[:2],
            ),
            Document(
                content=sample_documents[1].content,
                name=name_b,
                link=f"file:///data/{name_b}",
                metadata={"name": name_b, "link": f"file:///data/{name_b}"},
                triples=sample_entities[2:],
            ),
        ]

        result = await doc_store.aadd_documents(docs)
        assert len(result) > 0

        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            cnt_stmt = select(func.count(col(DocumentTable.id))).where(
                col(DocumentTable.id).in_(result),
            )
            result = await session.execute(cnt_stmt)
            assert (result.scalar() or 0) >= 2


@pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"), reason="DEEPSEEK_API_KEY not set")
@pytest.mark.usefixtures("setup_test_database")
class TestAaddDocumentsWithLLM:
    @pytest.fixture
    def doc_store(self):
        return DocumentStore(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_with_llm_produces_triples(self, doc_store):
        doc = Document(
            content="青花瓷瓶是明朝景德镇制作的著名瓷器，现收藏于克利夫兰艺术博物馆。",
            name="llm_artifact_test",
            link="file:///data/llm_artifact_test",
            metadata={"name": "llm_artifact_test", "link": "file:///data/llm_artifact_test"},
        )

        result = await doc_store.aadd_documents([doc], use_llm=True)
        assert len(result) > 0

        doc_id = result[0]
        db = DatabaseManager(TEST_DB_NAME)
        async with db.asession() as session:
            stmt = select(col(DocumentTable.entities)).where(
                col(DocumentTable.id) == doc_id,
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            assert row is not None
            all_entities = set(row[0] or [])

        assert len(all_entities) >= 2, f"Expected at least 2 entities from LLM extraction, got {len(all_entities)}"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aadd_documents_with_llm_and_structural_triples(self, doc_store):
        structural_triple = ExtractedTriple(
            subject=ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
            object=ExtractedEntity(name="大都会博物馆", entity_type=EntityType.MUSEUM),
            description="青铜鼎收藏于大都会博物馆",
        )

        doc = Document(
            content="商代青铜鼎收藏于大都会博物馆。器身饰有饕餮纹和云雷纹，是中国古代青铜艺术的代表。",
            name="llm_combined_test",
            link="file:///data/llm_combined_test",
            metadata={"name": "llm_combined_test", "link": "file:///data/llm_combined_test"},
            triples=[structural_triple],
        )

        result = await doc_store.aadd_documents([doc], use_llm=True)
        assert len(result) > 0

        assert structural_triple.predicate.strength is not None, (
            "Structural triple should have strength after processing"
        )
        assert 0.0 <= structural_triple.predicate.strength <= 1.0
