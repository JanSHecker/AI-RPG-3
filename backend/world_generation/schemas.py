from typing import Literal, Optional

from pydantic import BaseModel, Field


PLACE_TYPES = ["town", "fortress", "forest", "dungeon", "ruin", "road", "landmark", "village"]
TERRAINS = ["hills", "marsh", "old road", "pine forest", "riverland", "high moor", "stone valley"]
JOBS = ["warden", "miller", "scout", "smith", "herbalist", "scribe", "hunter", "priest", "trader", "miner"]
PERSONALITIES = ["wary but generous", "dry-humored and stubborn", "ambitious and polished", "quietly fearful", "curious and restless"]
FACTION_COUNT = 4
FACTION_LOCATION_COUNT = 5
NEUTRAL_VILLAGE_COUNT = 5
DUNGEON_LOCATION_COUNT = 5
PLACE_COUNT = FACTION_COUNT * FACTION_LOCATION_COUNT + NEUTRAL_VILLAGE_COUNT + DUNGEON_LOCATION_COUNT
NPC_COUNT = 60
RELATIONSHIP_COUNT = 16


class RegionDraft(BaseModel):
    name: str
    description: str


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
    personality: str
    job: str
    faction_ref: Optional[str] = None
    home_place_ref: str
    current_place_ref: str
    status: str
    lore: str


class RelationshipDraft(BaseModel):
    ref: str
    source_type: str
    source_ref: str
    target_type: str
    target_ref: str
    relation_type: str
    description: str


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
    relationships: list[RelationshipDraft] = Field(min_length=RELATIONSHIP_COUNT, max_length=RELATIONSHIP_COUNT)
