from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

CIDOC_GRAPH = UUID("6f5e0c50-8d9a-4b3a-8c1a-9d7e3f2a1b4c")


class EntityType(StrEnum):
    ARTIFACT = "artifact"
    MUSEUM = "museum"
    DYNASTY = "dynasty"
    ARTIST = "artist"
    LOCATION = "location"
    MATERIAL = "material"
    ARTIFACT_TYPE = "artifact_type"


_INVALID_URI_CHARS = {":", "{", "}", "[", "]", '"', "'", "\n", "\r", "\t"}


def get_entity_uri(entity_type: EntityType, name: str) -> str:
    safe_name = name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    for ch in _INVALID_URI_CHARS:
        safe_name = safe_name.replace(ch, "_")
    return f"cidoc:{entity_type.value}/{safe_name}"


def parse_entity_uri(uri: str) -> tuple[EntityType, str] | None:
    if not uri.startswith("cidoc:"):
        return None
    body = uri[len("cidoc:") :]
    if "/" not in body:
        return None
    entity_type_str, safe_name = body.split("/", 1)
    if not entity_type_str or not safe_name:
        return None
    try:
        entity_type = EntityType(entity_type_str)
    except ValueError:
        return None
    name = safe_name.replace("_", " ")
    return entity_type, name


class RelationshipType(StrEnum):
    COLLECTED_BY = "collected_by"
    CREATED_BY = "created_by"
    BELONGS_TO_DYNASTY = "belongs_to_dynasty"
    MADE_OF_MATERIAL = "made_of_material"
    IS_TYPE_OF = "is_type_of"
    LOCATED_AT = "located_at"
    DEPICTS = "depicts"
    RELATED_TO = "related_to"


class RelationshipInfo(BaseModel):
    predicate: RelationshipType
    strength: float | None = None

    @property
    def uri(self) -> str:
        return f"cidoc:relationship/{self.predicate}"

    @model_validator(mode="before")
    @classmethod
    def _parse_string(cls, data: object) -> object:
        if isinstance(data, str):
            return {"predicate": data}
        return data


class ExtractedEntity(BaseModel):
    name: str
    entity_type: EntityType
    properties: dict[str, str] = Field(default_factory=dict)
    description: str | None = None

    @property
    def uri(self) -> str:
        return get_entity_uri(self.entity_type, self.name)


class ExtractedTriple(BaseModel):
    subject: ExtractedEntity
    predicate: RelationshipInfo
    object: ExtractedEntity
    description: str | None = None

    @property
    def subject_uri(self) -> str:
        return self.subject.uri

    @property
    def object_uri(self) -> str:
        return self.object.uri
