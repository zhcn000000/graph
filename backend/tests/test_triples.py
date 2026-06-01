import json
import os

import pytest

from knowgraph.graph.schema import (
    EntityType,
    ExtractedTriple,
)
from knowgraph.graph.triples import LLMExtractor


@pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"), reason="DEEPSEEK_API_KEY not set")
class TestLLMExtractorLive:
    """Real LLM API tests — verifies structured output formatting from DeepSeek model."""

    async def test_aextract_from_document_produces_valid_triples(self):
        """Verify LLM produces well-formed ExtractedTriple list with correct enum values."""
        from knowgraph.documents.models import Document
        from knowgraph.graph.schema import RelationshipType

        extractor = LLMExtractor()
        extractor.SYSTEM_PROMPT += "\n本次为测试结构化输出格式，因此请至少输出一个三元组，即使和问题无关"  # type: ignore
        doc = Document(
            content="青花瓷瓶，明朝陶瓷，收藏于 Cleveland Museum of Art，位于 Cleveland",
            name="测试文物",
        )

        triples = await extractor.aextract_from_document(doc)

        assert isinstance(triples, list)
        assert len(triples) > 0, "LLM should extract at least one triple"
        for t in triples:
            assert isinstance(t, ExtractedTriple)
            assert t.subject.name
            assert t.subject.entity_type in EntityType
            assert t.predicate.predicate in RelationshipType
            assert t.object.name
            assert t.object.entity_type in EntityType

    async def test_aextract_from_row_dict_produces_valid_triples(self):
        """Verify LLM produces well-formed ExtractedTriple list from a dictionary-style record."""
        from knowgraph.graph.schema import RelationshipType

        extractor = LLMExtractor()
        extractor.SYSTEM_PROMPT += "\n本次为测试结构化输出格式，因此请至少输出一个三元组，即使和问题无关"  # type: ignore

        record_str = json.dumps({
            "title": "青花瓷瓶",
            "period": "明朝",
            "type": "瓷器",
            "material": "陶瓷",
            "description": "精美的青花瓷瓶，描绘山水和人物图案",
            "museum": "Cleveland Museum of Art",
            "location": "Cleveland",
        }, ensure_ascii=False, indent=2)

        user_prompt = extractor._build_user_prompt(record_str, [])

        triples = await extractor._run_agent_with_prompt(user_prompt)

        assert isinstance(triples, list)
        assert len(triples) > 0, "LLM should extract at least one triple"
        for t in triples:
            assert isinstance(t, ExtractedTriple)
            assert t.subject.name
            assert t.subject.entity_type in EntityType
            assert t.predicate.predicate in RelationshipType
            assert t.object.name
            assert t.object.entity_type in EntityType
