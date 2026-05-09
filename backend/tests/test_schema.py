import pytest

from knowgraph.graph import RelationshipType
from knowgraph.graph.schema import (
    CIDOC_GRAPH,
    EntityType,
    ExtractedEntity,
    ExtractedTriple,
    RelationshipInfo,
    get_entity_uri,
)


class TestEntityType:
    def test_enum_values(self):
        assert EntityType.ARTIFACT == "artifact"
        assert EntityType.MUSEUM == "museum"
        assert EntityType.DYNASTY == "dynasty"
        assert EntityType.ARTIST == "artist"
        assert EntityType.LOCATION == "location"
        assert EntityType.MATERIAL == "material"
        assert EntityType.ARTIFACT_TYPE == "artifact_type"

    def test_enum_members_count(self):
        assert len(EntityType) == 7

    def test_enum_str_conversion(self):
        assert str(EntityType.ARTIFACT) == "artifact"
        assert str(EntityType.MUSEUM) == "museum"


class TestCIDOCGraph:
    def test_cidoc_graph_uuid(self):
        from uuid import UUID

        assert isinstance(CIDOC_GRAPH, UUID)
        assert str(CIDOC_GRAPH) == "6f5e0c50-8d9a-4b3a-8c1a-9d7e3f2a1b4c"


class TestGetEntityURI:
    def test_basic_entity_uri(self):
        uri = get_entity_uri(EntityType.ARTIFACT, "青铜鼎")
        assert uri == "cidoc:artifact/青铜鼎"

    def test_uri_with_spaces(self):
        uri = get_entity_uri(EntityType.MUSEUM, "Metropolitan Museum of Art")
        assert uri == "cidoc:museum/Metropolitan_Museum_of_Art"

    def test_uri_strips_whitespace(self):
        uri = get_entity_uri(EntityType.DYNASTY, "  唐朝  ")
        assert uri == "cidoc:dynasty/唐朝"

    def test_uri_replaces_slashes(self):
        uri = get_entity_uri(EntityType.LOCATION, "New/York")
        assert uri == "cidoc:location/New_York"

    def test_uri_replaces_backslashes(self):
        uri = get_entity_uri(EntityType.MATERIAL, "a\\b")
        assert uri == "cidoc:material/a_b"

    def test_uri_all_entity_types(self):
        for etype in EntityType:
            uri = get_entity_uri(etype, "test_name")
            assert uri.startswith(f"cidoc:{etype.value}/")

    def test_uri_invalid_characters(self):
        invalid_names = [
            "test:name",
            "test{name}",
            "test[name]",
            'test"name',
            "test\nname",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError):
                get_entity_uri(EntityType.ARTIFACT, name)


class TestRelationshipInfo:
    def test_relationship_creation(self):
        rel = RelationshipInfo(predicate=RelationshipType.COLLECTED_BY)
        assert rel.predicate == RelationshipType.COLLECTED_BY
        assert rel.strength is None
        assert rel.uri == "cidoc:relationship/collected_by"

    def test_relationship_with_strength(self):
        rel = RelationshipInfo(predicate=RelationshipType.CREATED_BY, strength=0.95)
        assert rel.predicate == RelationshipType.CREATED_BY
        assert rel.strength == 0.95
        assert rel.uri == "cidoc:relationship/created_by"

    def test_parse_from_string(self):
        rel = RelationshipInfo.model_validate("collected_by")
        assert rel.predicate == RelationshipType.COLLECTED_BY
        assert rel.strength is None


class TestExtractedEntity:
    def test_entity_creation(self):
        entity = ExtractedEntity(
            name="青铜鼎",
            entity_type=EntityType.ARTIFACT,
        )
        assert entity.name == "青铜鼎"
        assert entity.entity_type == EntityType.ARTIFACT
        assert entity.properties == {}
        assert entity.description is None

    def test_entity_with_properties(self):
        entity = ExtractedEntity(
            name="Metropolitan Museum of Art",
            entity_type=EntityType.MUSEUM,
            properties={"location": "New York"},
        )
        assert entity.properties == {"location": "New York"}

    def test_entity_uri_property(self):
        entity = ExtractedEntity(
            name="唐朝",
            entity_type=EntityType.DYNASTY,
        )
        assert entity.uri == "cidoc:dynasty/唐朝"


class TestExtractedTriple:
    def test_triple_creation(self):
        subject = ExtractedEntity(name="青铜鼎", entity_type=EntityType.ARTIFACT)
        object_ = ExtractedEntity(name="Metropolitan Museum of Art", entity_type=EntityType.MUSEUM)

        triple = ExtractedTriple(
            subject=subject,
            predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
            object=object_,
            description="青铜鼎收藏于Metropolitan Museum of Art",
        )

        assert triple.subject.name == "青铜鼎"
        assert triple.predicate.predicate == RelationshipType.COLLECTED_BY
        assert triple.object.name == "Metropolitan Museum of Art"
        assert triple.description == "青铜鼎收藏于Metropolitan Museum of Art"

    def test_triple_without_description(self):
        subject = ExtractedEntity(name="青花瓷瓶", entity_type=EntityType.ARTIFACT)
        object_ = ExtractedEntity(name="明朝", entity_type=EntityType.DYNASTY)

        triple = ExtractedTriple(
            subject=subject,
            predicate=RelationshipInfo(predicate=RelationshipType.BELONGS_TO_DYNASTY),
            object=object_,
        )

        assert triple.description is None

    def test_triple_uri_properties(self):
        triple = ExtractedTriple(
            subject=ExtractedEntity(name="Test", entity_type=EntityType.ARTIFACT),
            predicate=RelationshipInfo(predicate=RelationshipType.COLLECTED_BY),
            object=ExtractedEntity(name="Museum", entity_type=EntityType.MUSEUM),
        )
        assert triple.subject_uri == "cidoc:artifact/Test"
        assert triple.object_uri == "cidoc:museum/Museum"
        assert triple.predicate.uri == "cidoc:relationship/collected_by"
