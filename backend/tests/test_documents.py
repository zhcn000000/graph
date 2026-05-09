from knowgraph.documents.models import Document
from knowgraph.graph import RelationshipType
from knowgraph.graph.schema import (
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipInfo,
)


class TestDocument:
    def test_document_creation_minimal(self):
        doc = Document(content="test content")
        assert doc.content == "test content"
        assert doc.name is None
        assert doc.link is None
        assert doc.query_score is None
        assert doc.metadata == {}
        assert doc.entities == []
        assert doc.triples == []
        assert doc.id is None
        assert doc.document_index is None
        assert doc.chunk_index is None

    def test_document_creation_full(self):
        from uuid import uuid4

        doc_id = uuid4()
        doc = Document(
            content="test content",
            name="test.md",
            link="file:///test.md",
            query_score=0.95,
            metadata={"author": "test"},
            entities=["cidoc:artifact/test"],
            triples=[
                ExtractedTriple(
                    subject=ExtractedEntity(name="test", entity_type=EntityType.ARTIFACT),
                    predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
                    object=ExtractedEntity(name="museum", entity_type=EntityType.MUSEUM),
                ),
            ],
            id=doc_id,
            document_index=1,
            chunk_index=0,
        )
        assert doc.name == "test.md"
        assert doc.link == "file:///test.md"
        assert doc.query_score == 0.95
        assert doc.metadata == {"author": "test"}
        assert doc.entities == ["cidoc:artifact/test"]
        assert len(doc.triples) == 1
        assert doc.triples[0].predicate.predicate == RelationshipType.COLLECTED_BY
        assert doc.id == doc_id
        assert doc.document_index == 1
        assert doc.chunk_index == 0
