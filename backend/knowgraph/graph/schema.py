from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

CIDOC_GRAPH = UUID("6f5e0c50-8d9a-4b3a-8c1a-9d7e3f2a1b4c")


class EntityType(StrEnum):
    ARTIFACT = "artifact"
    MUSEUM = "museum"
    DYNASTY = "dynasty"
    ARTIST = "artist"
    LOCATION = "location"


class RelationshipType(StrEnum):
    COLLECTED_BY = "collected_by"
    CREATED_BY = "created_by"
    BELONGS_TO_DYNASTY = "belongs_to_dynasty"
    MADE_OF_MATERIAL = "made_of_material"
    IS_TYPE_OF = "is_type_of"
    LOCATED_AT = "located_at"
    DEPICTS = "depicts"
    RELATED_TO = "related_to"


ENTITY_NAMESPACES: dict[EntityType, str] = {
    EntityType.ARTIFACT: "artifact",
    EntityType.MUSEUM: "museum",
    EntityType.DYNASTY: "dynasty",
    EntityType.ARTIST: "artist",
    EntityType.LOCATION: "location",
}

RELATIONSHIP_NAMESPACES: dict[RelationshipType, str] = {
    RelationshipType.COLLECTED_BY: "collected_by",
    RelationshipType.CREATED_BY: "created_by",
    RelationshipType.BELONGS_TO_DYNASTY: "belongs_to_dynasty",
    RelationshipType.MADE_OF_MATERIAL: "made_of_material",
    RelationshipType.IS_TYPE_OF: "is_type_of",
    RelationshipType.LOCATED_AT: "located_at",
    RelationshipType.DEPICTS: "depicts",
    RelationshipType.RELATED_TO: "related_to",
}


class Schema:
    @staticmethod
    def get_entity_type_name(entity_type: EntityType) -> str:
        return entity_type.value

    @staticmethod
    def get_relationship_type_name(rel_type: RelationshipType) -> str:
        return rel_type.value


@dataclass
class Entity:
    uri: str
    entity_type: EntityType
    name: str
    properties: dict[str, str] = field(default_factory=dict)
    description: str | None = None


@dataclass
class Artifact(Entity):
    def __init__(
        self,
        name: str,
        properties: dict[str, str] | None = None,
        description: str | None = None,
    ):
        super().__init__(
            uri=get_entity_uri(EntityType.ARTIFACT, name),
            entity_type=EntityType.ARTIFACT,
            name=name,
            properties=properties or {},
            description=description,
        )


@dataclass
class Museum(Entity):
    def __init__(
        self,
        name: str,
        location: str | None = None,
        properties: dict[str, str] | None = None,
        description: str | None = None,
    ):
        props = properties or {}
        if location:
            props["location"] = location
        super().__init__(
            uri=get_entity_uri(EntityType.MUSEUM, name),
            entity_type=EntityType.MUSEUM,
            name=name,
            properties=props,
            description=description,
        )


@dataclass
class Dynasty(Entity):
    def __init__(
        self,
        name: str,
        start_year: int | None = None,
        end_year: int | None = None,
        properties: dict[str, str] | None = None,
        description: str | None = None,
    ):
        props = properties or {}
        if start_year is not None:
            props["start_year"] = str(start_year)
        if end_year is not None:
            props["end_year"] = str(end_year)
        super().__init__(
            uri=get_entity_uri(EntityType.DYNASTY, name),
            entity_type=EntityType.DYNASTY,
            name=name,
            properties=props,
            description=description,
        )


@dataclass
class Artist(Entity):
    def __init__(
        self,
        name: str,
        birth_year: int | None = None,
        death_year: int | None = None,
        nationality: str | None = None,
        properties: dict[str, str] | None = None,
        description: str | None = None,
    ):
        props = properties or {}
        if birth_year is not None:
            props["birth_year"] = str(birth_year)
        if death_year is not None:
            props["death_year"] = str(death_year)
        if nationality:
            props["nationality"] = nationality
        super().__init__(
            uri=get_entity_uri(EntityType.ARTIST, name),
            entity_type=EntityType.ARTIST,
            name=name,
            properties=props,
            description=description,
        )


@dataclass
class Location(Entity):
    def __init__(
        self,
        name: str,
        country: str | None = None,
        city: str | None = None,
        properties: dict[str, str] | None = None,
        description: str | None = None,
    ):
        props = properties or {}
        if country:
            props["country"] = country
        if city:
            props["city"] = city
        super().__init__(
            uri=get_entity_uri(EntityType.LOCATION, name),
            entity_type=EntityType.LOCATION,
            name=name,
            properties=props,
            description=description,
        )


def get_entity_uri(entity_type: EntityType, name: str) -> str:
    namespace = ENTITY_NAMESPACES[entity_type]
    safe_name = name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return f"cidoc:{namespace}/{safe_name}"


def get_relationship_uri(rel_type: RelationshipType) -> str:
    return f"cidoc:relationship/{rel_type.value}"


class ArtifactModel(BaseModel):
    object_id: str
    title: str
    period: str | None = None
    type: str | None = None
    material: str | None = None
    description: str | None = None
    dimensions: str | None = None
    museum: str
    location: str | None = None
    detail_url: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    credit_line: str | None = None
    accession_number: str | None = None
    crawl_date: str | None = None


class ExtractedEntity(BaseModel):
    name: str
    entity_type: EntityType
    properties: dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class ExtractedTriple(BaseModel):
    subject: ExtractedEntity
    predicate: RelationshipType
    object: ExtractedEntity
    description: str | None = None
