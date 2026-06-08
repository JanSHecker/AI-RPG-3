from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from personality_catalog import load_personality_catalog
from relationship_catalog import load_primary_relationship_catalog, load_relationship_catalog, load_secondary_relationship_catalog


PLACE_TYPES = ["town", "fortress", "forest", "dungeon", "ruin", "road", "landmark", "village"]
TERRAINS = ["hills", "marsh", "old road", "pine forest", "riverland", "high moor", "stone valley"]
JOBS = ["warden", "miller", "scout", "smith", "herbalist", "scribe", "hunter", "priest", "trader", "miner"]
PERSONALITIES = load_personality_catalog()
PERSONALITY_SET = set(PERSONALITIES)
PERSONALITY_ALIASES = {
    "steady": "stable",
    "sensitive": "empathetic",
}
PRIMARY_RELATIONSHIP_TYPES = load_primary_relationship_catalog()
SECONDARY_RELATIONSHIP_TYPES = load_secondary_relationship_catalog()
RELATIONSHIP_TYPES = load_relationship_catalog()
RELATIONSHIP_TYPE_SET = set(RELATIONSHIP_TYPES)
FACTION_COUNT = 4
FACTION_LOCATION_COUNT = 5
NEUTRAL_VILLAGE_COUNT = 5
DUNGEON_LOCATION_COUNT = 5
PLACE_COUNT = FACTION_COUNT * FACTION_LOCATION_COUNT + NEUTRAL_VILLAGE_COUNT + DUNGEON_LOCATION_COUNT
NPC_COUNT = 60
RELATIONSHIP_COUNT = 16
RELATIONSHIP_TARGET_COUNT = NPC_COUNT * 2

AGE_BANDS = ["child", "teen", "young adult", "adult", "elder"]
CHARACTER_CLUSTER_KINDS = ["household", "family", "workplace", "faction cell", "social circle", "rivalry group"]


REGION_IDENTITY_HEADINGS = [
    ("overview", "Overview"),
    ("geography", "Geography"),
    ("climate", "Climate"),
    ("peoples_and_culture", "Peoples and Culture"),
    ("power_centers", "Power Centers"),
    ("current_conflicts", "Current Conflicts"),
    ("tone_and_themes", "Tone and Themes"),
    ("generation_boundaries", "Generation Boundaries"),
]


class RegionIdentityDraft(BaseModel):
    overview: str
    geography: str
    climate: str
    peoples_and_culture: str
    power_centers: str
    current_conflicts: str
    tone_and_themes: str
    generation_boundaries: str


def render_region_description(name: str, identity: RegionIdentityDraft) -> str:
    sections = [f"# {name.strip() or 'Region'}"]
    for field_name, heading in REGION_IDENTITY_HEADINGS:
        sections.append(f"## {heading}\n\n{getattr(identity, field_name).strip()}")
    return "\n\n".join(sections).strip() + "\n"


def _summary_from_description(description: str) -> str:
    compact = " ".join(description.split())
    if not compact:
        return "A region defined by the world prompt."
    for delimiter in (". ", "! ", "? "):
        if delimiter in compact:
            sentence = compact.split(delimiter, 1)[0].strip() + delimiter.strip()
            return sentence[:280].strip()
    return compact[:280].strip()


def _legacy_region_identity(description: str) -> dict[str, str]:
    summary = _summary_from_description(description)
    return {
        "overview": summary,
        "geography": "Use the original world prompt and later place generation to establish specific regional geography.",
        "climate": "Use the original world prompt and later place generation to establish specific climate details.",
        "peoples_and_culture": "Use the original world prompt and later NPC and faction generation to establish local peoples and culture.",
        "power_centers": "Use later faction and place generation to establish high-level power centers.",
        "current_conflicts": "Use later faction, place, NPC, and relationship generation to establish broad regional conflicts.",
        "tone_and_themes": "Preserve the tone implied by the original region description.",
        "generation_boundaries": "Do not treat this legacy primer as containing specific place records, NPC biographies, quest hooks, item details, resolved relationships, tactical encounters, or faction rosters.",
    }


class RegionDraft(BaseModel):
    name: str
    summary: str
    identity: RegionIdentityDraft
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_region(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        legacy_description = str(normalized.get("description") or "")
        if "summary" not in normalized:
            normalized["summary"] = _summary_from_description(legacy_description)
        if "identity" not in normalized:
            normalized["identity"] = _legacy_region_identity(legacy_description)
        return normalized

    @model_validator(mode="after")
    def render_description(self) -> "RegionDraft":
        self.description = render_region_description(self.name, self.identity)
        return self


class PlaceDraft(BaseModel):
    ref: str
    name: str
    place_type: str
    summary: str
    x: int = Field(ge=0, le=100)
    y: int = Field(ge=0, le=100)
    terrain: str
    danger_level: int = Field(ge=1, le=5)
    population_estimate: int = Field(ge=0)
    controlling_faction_ref: Optional[str] = None
    parent_place_ref: Optional[str] = None
    lore: str


class LocationPlanSlot(BaseModel):
    ref: str
    place_type: str
    x: int = Field(ge=0, le=100)
    y: int = Field(ge=0, le=100)
    cluster_id: str
    cluster_kind: str
    faction_ref: Optional[str] = None
    terrain_hint: str
    danger_level_hint: int = Field(ge=1, le=5)
    population_hint: int = Field(ge=0)
    purpose: str
    theme: str


class LocationPlanBatch(BaseModel):
    batch_id: str
    batch_kind: str
    faction_ref: Optional[str] = None
    center_x: int = Field(ge=0, le=100)
    center_y: int = Field(ge=0, le=100)
    slots: list[LocationPlanSlot] = Field(min_length=1)


class LocationPlanStep(BaseModel):
    batches: list[LocationPlanBatch] = Field(min_length=1)
    slots: list[LocationPlanSlot] = Field(min_length=PLACE_COUNT, max_length=PLACE_COUNT)


class RequiredPlaceDraft(BaseModel):
    name: str
    description: str


class RequiredCharacterDraft(BaseModel):
    name: str
    description: str


class FactionRequirementRelationshipDraft(BaseModel):
    source_kind: Literal["place", "character"]
    source_name: str
    target_kind: Literal["place", "character"]
    target_name: str
    relation_type: str
    description: str

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, value: str) -> str:
        if value not in RELATIONSHIP_TYPE_SET:
            raise ValueError(f"Relationship type must come from the relationship catalog; got {value}.")
        return value


class FactionDraft(BaseModel):
    ref: str
    name: str
    type: str
    goals: str
    public_reputation: str
    power_level: int = Field(ge=1, le=5)
    home_place_ref: Optional[str] = None
    required_places: list[RequiredPlaceDraft] = Field(min_length=1)
    required_characters: list[RequiredCharacterDraft] = Field(min_length=1)
    requirement_relationships: list[FactionRequirementRelationshipDraft]
    lore: str


class NpcDraft(BaseModel):
    ref: str
    name: str
    age: int = Field(ge=12, le=95)
    personality: list[str] = Field(min_length=3, max_length=3)
    job: str
    faction_ref: Optional[str] = None
    home_place_ref: str
    current_place_ref: str
    status: str
    lore: str

    @field_validator("personality", mode="before")
    @classmethod
    def normalize_personality_aliases(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [PERSONALITY_ALIASES.get(entry, entry) if isinstance(entry, str) else entry for entry in value]

    @field_validator("personality")
    @classmethod
    def validate_personality(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("NPC personality values must be unique.")
        invalid = [entry for entry in value if entry not in PERSONALITY_SET]
        if invalid:
            raise ValueError(f"NPC personality values must come from the personality catalog; got {invalid}.")
        return value


class RelationshipDraft(BaseModel):
    ref: str
    source_type: str
    source_ref: str
    target_type: str
    target_ref: str
    relation_type: str
    description: str

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, value: str) -> str:
        if value not in RELATIONSHIP_TYPE_SET:
            raise ValueError(f"Relationship type must come from the relationship catalog; got {value}.")
        return value


class CharacterSlotDraft(BaseModel):
    ref: str
    home_place_ref: str
    current_place_ref: str
    faction_ref: Optional[str] = None
    age_band: str
    role_hint: str
    cluster_ref: str

    @field_validator("age_band")
    @classmethod
    def validate_age_band(cls, value: str) -> str:
        if value not in AGE_BANDS:
            raise ValueError(f"Character slot age_band must be one of {AGE_BANDS}; got {value}.")
        return value


class CharacterClusterDraft(BaseModel):
    ref: str
    kind: str
    place_ref: str
    summary: str

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if value not in CHARACTER_CLUSTER_KINDS:
            raise ValueError(f"Character cluster kind must be one of {CHARACTER_CLUSTER_KINDS}; got {value}.")
        return value


class PlannedRelationshipDraft(BaseModel):
    ref: str
    source_ref: str
    target_ref: str
    relation_type: str
    description: str

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, value: str) -> str:
        if value not in RELATIONSHIP_TYPE_SET:
            raise ValueError(f"Relationship type must come from the relationship catalog; got {value}.")
        return value


class RelationshipOpportunityDraft(BaseModel):
    ref: str
    kind: str
    slot_refs: list[str] = Field(default_factory=list)
    place_refs: list[str] = Field(default_factory=list)
    faction_refs: list[str] = Field(default_factory=list)
    summary: str


class CharacterSegmentDraft(BaseModel):
    ref: str
    cluster_refs: list[str] = Field(min_length=1)
    slot_refs: list[str] = Field(min_length=1)
    summary: str


class CharacterDiagramStep(BaseModel):
    clusters: list[CharacterClusterDraft] = Field(min_length=1)
    slots: list[CharacterSlotDraft] = Field(min_length=NPC_COUNT, max_length=NPC_COUNT)
    relationships: list[PlannedRelationshipDraft] = Field(min_length=1)


class ItemDefinitionDraft(BaseModel):
    ref: str
    name: str
    category: str
    rarity: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    value: int = Field(ge=0)
    weight: float = Field(ge=0)
    stackable: bool
    consumable: bool
    equip_slot: Optional[str] = None
    effect_summary: str


class WorldItemDraft(ItemDefinitionDraft):
    lore: str


class NpcInventoryItemDraft(BaseModel):
    id: str
    world_id: str
    npc_id: str
    item_source_type: str
    item_id: str
    quantity: int = Field(ge=1)
    condition: str
    note: str = ""


class WorldDraft(BaseModel):
    title: str
    region: RegionDraft
    places: list[PlaceDraft] = Field(min_length=PLACE_COUNT, max_length=PLACE_COUNT)
    factions: list[FactionDraft] = Field(min_length=FACTION_COUNT, max_length=FACTION_COUNT)
    npcs: list[NpcDraft] = Field(min_length=NPC_COUNT, max_length=NPC_COUNT)
    relationships: list[RelationshipDraft] = Field(min_length=1)
