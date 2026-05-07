from knowgraph.documents.models import Document


class TestDocument:
    def test_document_creation_minimal(self):
        doc = Document(content="test content")
        assert doc.content == "test content"
        assert doc.name is None
        assert doc.link is None
        assert doc.query_score is None
        assert doc.metadata == {}
        assert doc.entities == []
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
            id=doc_id,
            document_index=1,
            chunk_index=0,
        )
        assert doc.name == "test.md"
        assert doc.link == "file:///test.md"
        assert doc.query_score == 0.95
        assert doc.metadata == {"author": "test"}
        assert doc.entities == ["cidoc:artifact/test"]
        assert doc.id == doc_id
        assert doc.document_index == 1
        assert doc.chunk_index == 0
