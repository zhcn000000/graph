import re
from difflib import get_close_matches
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

_KNOWN_DYNASTIES: list[str] = [
    "Xia Dynasty",
    "Shang Dynasty",
    "Zhou Dynasty",
    "Qin Dynasty",
    "Han Dynasty",
    "Three Kingdoms",
    "Jin Dynasty",
    "Southern and Northern Dynasties",
    "Sui Dynasty",
    "Tang Dynasty",
    "Five Dynasties and Ten Kingdoms",
    "Liao Dynasty",
    "Song Dynasty",
    "Western Xia",
    "Yuan Dynasty",
    "Ming Dynasty",
    "Qing Dynasty",
    "Spring and Autumn period",
    "Warring States period",
    "Eastern Zhou period",
    "Western Zhou period",
    "Neolithic period",
    "Joseon dynasty",
    "Edo period",
    "Mughal period",
    "Safavid period",
    "Ilkhanid period",
    "People's Republic of China",
]

_KNOWN_ARTIFACT_TYPES: list[str] = [
    "Container",
    "Toy",
    "Painting",
    "Sculpture",
    "Ceramic",
    "Vessel",
    "Textile",
    "Calligraphy",
    "Jade Carving",
    "Furniture",
    "Print",
    "Woodblock Print",
    "Armor",
    "Weapon",
    "Lacquerware",
    "Cloisonné",
    "Snuff Bottle",
    "Fan",
    "Seal",
    "Mirror",
    "Ritual Object",
    "Architectural Element",
    "Coin",
    "Musical Instrument",
    "Buddhist Figure",
    "Scroll",
    "Hanging Scroll",
    "Handscroll",
    "Album Leaf",
    "Screen",
    "Porcelain",
    "Earthenware",
    "Ornament",
    "Vase",
    "Bowl",
    "Plate",
    "Cup",
    "Jar",
    "Box",
    "Brush Rest",
    "Brush Pot",
    "Inkstone",
    "Censer",
    "Incense Burner",
]

_KNOWN_MATERIALS: list[str] = [
    "Bronze",
    "Jade",
    "Porcelain",
    "Silk",
    "Gold",
    "Silver",
    "Iron",
    "Copper",
    "Lacquer",
    "Bamboo",
    "Wood",
    "Stone",
    "Ivory",
    "Glass",
    "Clay",
    "Ink",
    "Paper",
    "Crystal",
    "Enamel",
    "Coral",
    "Marble",
    "Gilt Bronze",
    "Brass",
    "Pewter",
    "Horn",
    "Bone",
    "Mother of Pearl",
    "Turquoise",
    "Agate",
    "Amber",
    "Cinnabar",
    "Brocade",
    "Cotton",
    "Hemp",
    "Lead",
    "Tin",
    "Steel",
]

CLASSIFIABLE_ENTITY_TYPES: frozenset[EntityType] = frozenset({
    EntityType.ARTIFACT_TYPE,
    EntityType.MATERIAL,
    EntityType.DYNASTY,
})


def normalize_dynasty_name(name: str) -> str:
    prev = None
    while prev != name:
        prev = name
        name = re.sub(r"\s*\([^)]*\)", "", name).strip()

    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s*[;,—–\-]\s*$", "", name).strip()

    name = re.sub(r"\b\d{1,4}\s*(BCE?|CE|AD)?\b", "", name).strip()
    name = re.sub(r"\b\d+(st|nd|rd|th)\s*century\b", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\b(c\.|ca\.?|circa|approx\.?)\s*\d+\b", "", name, flags=re.IGNORECASE).strip()

    name = re.sub(r"\b(Early|Late|Mid|Middle)\s+", "", name, flags=re.IGNORECASE).strip()

    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s*[;,—–\-]\s*$", "", name).strip()

    if not name:
        return "unknown"

    match = get_close_matches(name, _KNOWN_DYNASTIES, n=1, cutoff=0.5)
    return match[0] if match else name


def normalize_entity_name(name: str, entity_type: EntityType) -> str:
    if entity_type == EntityType.DYNASTY:
        name = normalize_dynasty_name(name)
    else:
        prev = None
        while prev != name:
            prev = name
            name = re.sub(r"\s*\([^)]*\)", "", name).strip()
    name = re.sub(r"\s+", " ", name.strip())
    return name


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
    def canonical_name(self) -> str:
        return normalize_entity_name(self.name, self.entity_type)

    @property
    def uri(self) -> str:
        return get_entity_uri(self.entity_type, self.canonical_name)


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
