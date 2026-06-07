import json
import random
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from config import settings


class ItemDefinitionBase(BaseModel):
    id: str
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


class StapleItemDefinition(ItemDefinitionBase):
    lore_path: Optional[Path] = None


class NpcInventoryItem(BaseModel):
    id: str
    world_id: str
    npc_id: str
    item_source_type: str
    item_id: str
    quantity: int = Field(ge=1)
    condition: str
    note: str = ""


class WorldItemRecord(ItemDefinitionBase):
    world_id: str


def load_staple_catalog(path: Optional[Path] = None, lore_dir: Optional[Path] = None) -> list[StapleItemDefinition]:
    catalog_path = path or settings.staple_items_file
    lore_path = lore_dir or settings.staple_item_lore_path
    if not catalog_path.exists():
        return []
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Staple item catalog must be a JSON list.")
    items: list[StapleItemDefinition] = []
    for entry in payload:
        item = StapleItemDefinition.model_validate(entry)
        lore_file = lore_path / f"{item.id}.md"
        if not lore_file.exists():
            raise ValueError(f"Missing lore file for staple item {item.id}.")
        items.append(item.model_copy(update={"lore_path": lore_file.resolve()}))
    return items


def load_staple_catalog_map(path: Optional[Path] = None, lore_dir: Optional[Path] = None) -> dict[str, StapleItemDefinition]:
    return {item.id: item for item in load_staple_catalog(path, lore_dir)}


COMMON_ITEM_IDS = {
    "staple-ration-pack",
    "staple-waterskin",
    "staple-bandage-roll",
    "staple-torch-bundle",
    "staple-flint-kit",
    "staple-hemp-rope",
    "staple-hunting-knife",
}


JOB_ITEM_PREFERENCES = {
    "warden": ["staple-work-axe", "staple-leather-jerkin", "staple-torch-bundle"],
    "miller": ["staple-ration-pack", "staple-flint-kit", "staple-hemp-rope"],
    "scout": ["staple-hunting-knife", "staple-waterskin", "staple-hemp-rope"],
    "smith": ["staple-work-axe", "staple-leather-jerkin", "staple-flint-kit"],
    "herbalist": ["staple-herbal-salve", "staple-bandage-roll", "staple-waterskin"],
    "scribe": ["staple-silver-trade-bars", "staple-ration-pack", "staple-lockpick-roll"],
    "hunter": ["staple-hunting-knife", "staple-hemp-rope", "staple-ration-pack"],
    "priest": ["staple-bandage-roll", "staple-herbal-salve", "staple-torch-bundle"],
    "trader": ["staple-silver-trade-bars", "staple-ration-pack", "staple-waterskin"],
    "miner": ["staple-torch-bundle", "staple-work-axe", "staple-bandage-roll"],
}


PERSONALITY_ITEM_PREFERENCES = {
    "cautious": ["staple-bandage-roll", "staple-ration-pack"],
    "stubborn": ["staple-work-axe", "staple-flint-kit"],
    "ambitious": ["staple-silver-trade-bars", "staple-leather-jerkin"],
    "fearful": ["staple-torch-bundle", "staple-waterskin"],
    "curious": ["staple-lockpick-roll", "staple-hemp-rope"],
    "generous": ["staple-bandage-roll", "staple-ration-pack"],
    "disciplined": ["staple-leather-jerkin", "staple-flint-kit"],
    "practical": ["staple-hemp-rope", "staple-flint-kit"],
    "secretive": ["staple-lockpick-roll", "staple-torch-bundle"],
    "bold": ["staple-hunting-knife", "staple-work-axe"],
}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _personality_values(npc: BaseModel) -> list[str]:
    personality = getattr(npc, "personality", [])
    if isinstance(personality, str):
        return [personality]
    return [value for value in personality if isinstance(value, str)]


def seed_npc_inventory(world_id: str, npcs: list[BaseModel], seed: int, staple_map: Optional[dict[str, StapleItemDefinition]] = None) -> list[NpcInventoryItem]:
    catalog = staple_map or load_staple_catalog_map()
    catalog_ids = set(catalog)
    inventory: list[NpcInventoryItem] = []
    for idx, npc in enumerate(npcs):
        npc_id = getattr(npc, "id", None) or getattr(npc, "ref")
        npc_rng = random.Random(seed + idx * 97)
        desired_ids = [
            "staple-ration-pack",
            "staple-waterskin",
            *JOB_ITEM_PREFERENCES.get(getattr(npc, "job", ""), []),
            *[
                item_id
                for personality in _personality_values(npc)
                for item_id in PERSONALITY_ITEM_PREFERENCES.get(personality, [])
            ],
        ]
        desired_ids = [item_id for item_id in _dedupe_preserve_order(desired_ids) if item_id in catalog_ids]
        desired_count = 1 + npc_rng.randint(0, 2)
        chosen_ids = desired_ids[:desired_count]
        if not chosen_ids:
            chosen_ids = npc_rng.sample(sorted(COMMON_ITEM_IDS & catalog_ids), k=min(2, len(COMMON_ITEM_IDS & catalog_ids)))

        for item_pos, item_id in enumerate(chosen_ids, start=1):
            definition = catalog[item_id]
            quantity = npc_rng.randint(1, 4) if definition.stackable else 1
            condition = npc_rng.choice(["worn", "serviceable", "well-kept"])
            inventory.append(
                NpcInventoryItem(
                    id=f"inv-{npc_id}-{item_pos:02d}",
                    world_id=world_id,
                    npc_id=npc_id,
                    item_source_type="staple",
                    item_id=item_id,
                    quantity=quantity,
                    condition=condition,
                    note=f"Commonly carried by a {getattr(npc, 'job', 'traveler')}.",
                )
            )
    return inventory
