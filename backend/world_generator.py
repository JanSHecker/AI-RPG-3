import hashlib
import json
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from pydantic import ValidationError

from config import settings
from database import db_session
from item_catalog import NpcInventoryItem, load_staple_catalog_map, seed_npc_inventory
from model_catalog import ConfiguredModel
from providers import ProviderError
from world_generation.pipeline import StepUpdater, build_world_draft as build_pipeline_world_draft
from world_generation.schemas import (
    PLACE_TYPES,
    WorldDraft,
    WorldItemDraft,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_from_prompt(prompt: str) -> int:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _entity_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

async def build_world_draft(prompt: str, model: ConfiguredModel, updater: Optional[StepUpdater] = None) -> tuple[WorldDraft, str, int]:
    return await build_pipeline_world_draft(prompt, model, updater)


def validate_links(
    draft: WorldDraft,
    world_items: Optional[list[WorldItemDraft]] = None,
    inventory_items: Optional[list[NpcInventoryItem]] = None,
) -> None:
    place_refs = {place.ref for place in draft.places}
    faction_refs = {faction.ref for faction in draft.factions}
    npc_refs = {npc.ref for npc in draft.npcs}
    relationship_refs = {rel.ref for rel in draft.relationships}
    world_item_refs = {item.ref for item in (world_items or [])}
    staple_item_ids = set(load_staple_catalog_map())

    if len(place_refs) != len(draft.places):
        raise ValueError("Place refs must be unique.")
    if len(faction_refs) != len(draft.factions):
        raise ValueError("Faction refs must be unique.")
    if len(npc_refs) != len(draft.npcs):
        raise ValueError("NPC refs must be unique.")
    if len(relationship_refs) != len(draft.relationships):
        raise ValueError("Relationship refs must be unique.")
    if len(world_item_refs) != len(world_items or []):
        raise ValueError("World item refs must be unique.")

    for place in draft.places:
        if place.place_type not in PLACE_TYPES:
            raise ValueError(f"Invalid place type: {place.place_type}")
        if place.controlling_faction_ref and place.controlling_faction_ref not in faction_refs:
            raise ValueError(f"Place {place.ref} references unknown faction.")
        if place.parent_place_ref and place.parent_place_ref not in place_refs:
            raise ValueError(f"Place {place.ref} references unknown parent place.")

    for faction in draft.factions:
        if faction.home_place_ref and faction.home_place_ref not in place_refs:
            raise ValueError(f"Faction {faction.ref} references unknown home place.")

    for npc in draft.npcs:
        if npc.faction_ref and npc.faction_ref not in faction_refs:
            raise ValueError(f"NPC {npc.ref} references unknown faction.")
        if npc.home_place_ref not in place_refs or npc.current_place_ref not in place_refs:
            raise ValueError(f"NPC {npc.ref} references unknown place.")

    valid_targets = {"place": place_refs, "faction": faction_refs, "npc": npc_refs}
    for rel in draft.relationships:
        if rel.source_ref not in valid_targets.get(rel.source_type, set()):
            raise ValueError(f"Relationship {rel.ref} has unknown source.")
        if rel.target_ref not in valid_targets.get(rel.target_type, set()):
            raise ValueError(f"Relationship {rel.ref} has unknown target.")

    for item in inventory_items or []:
        if item.npc_id not in npc_refs:
            raise ValueError(f"Inventory item {item.id} references unknown NPC.")
        if item.item_source_type == "staple" and item.item_id not in staple_item_ids:
            raise ValueError(f"Inventory item {item.id} references unknown staple item.")
        if item.item_source_type == "world" and item.item_id not in world_item_refs:
            raise ValueError(f"Inventory item {item.id} references unknown world item.")
        if item.item_source_type not in {"staple", "world"}:
            raise ValueError(f"Inventory item {item.id} has invalid item source type.")


def _assign_entity_ids(
    draft: WorldDraft,
    world_items: Optional[list[WorldItemDraft]] = None,
    inventory_items: Optional[list[NpcInventoryItem]] = None,
) -> dict[str, Any]:
    return {
        "region_id": _entity_id("region"),
        "place_ids": {place.ref: _entity_id("place") for place in draft.places},
        "faction_ids": {faction.ref: _entity_id("faction") for faction in draft.factions},
        "npc_ids": {npc.ref: _entity_id("npc") for npc in draft.npcs},
        "relationship_ids": {rel.ref: _entity_id("relationship") for rel in draft.relationships},
        "world_item_ids": {item.ref: _entity_id("item") for item in (world_items or [])},
        "inventory_ids": {item.id: _entity_id("inventory") for item in (inventory_items or [])},
    }


def _write_lore(
    world_id: str,
    draft: WorldDraft,
    id_map: dict[str, Any],
    world_items: Optional[list[WorldItemDraft]] = None,
    worlds_path: Optional[Path] = None,
) -> None:
    root = (worlds_path or settings.worlds_path) / world_id
    (root / "places").mkdir(parents=True, exist_ok=True)
    (root / "factions").mkdir(parents=True, exist_ok=True)
    (root / "npcs").mkdir(parents=True, exist_ok=True)
    (root / "items").mkdir(parents=True, exist_ok=True)
    (root / "region.md").write_text(draft.region.description, encoding="utf-8")
    for place in draft.places:
        (root / "places" / f"{id_map['place_ids'][place.ref]}.md").write_text(place.lore, encoding="utf-8")
    for faction in draft.factions:
        (root / "factions" / f"{id_map['faction_ids'][faction.ref]}.md").write_text(faction.lore, encoding="utf-8")
    for npc in draft.npcs:
        (root / "npcs" / f"{id_map['npc_ids'][npc.ref]}.md").write_text(npc.lore, encoding="utf-8")
    for item in world_items or []:
        (root / "items" / f"{id_map['world_item_ids'][item.ref]}.md").write_text(item.lore, encoding="utf-8")


def insert_world(
    prompt: str,
    model: ConfiguredModel,
    draft: WorldDraft,
    raw_response: str,
    latency_ms: int,
    db_path: Optional[Path] = None,
    worlds_path: Optional[Path] = None,
    world_items: Optional[list[WorldItemDraft]] = None,
    inventory_items: Optional[list[NpcInventoryItem]] = None,
) -> str:
    world_id = f"world-{uuid.uuid4().hex[:12]}"
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    timestamp = now_iso()
    seed = _seed_from_prompt(prompt)
    started_at = timestamp
    validate_links(draft, world_items, inventory_items)
    id_map = _assign_entity_ids(draft, world_items, inventory_items)
    resolved_npcs = [
        SimpleNamespace(
            id=id_map["npc_ids"][npc.ref],
            job=npc.job,
            personality=npc.personality,
        )
        for npc in draft.npcs
    ]
    if inventory_items is not None:
        resolved_inventory_items = []
        for item in inventory_items:
            item_id = item.item_id
            if item.item_source_type == "world":
                item_id = id_map["world_item_ids"].get(item.item_id, item.item_id)
            resolved_inventory_items.append(
                item.model_copy(
                    update={
                        "id": id_map["inventory_ids"][item.id],
                        "world_id": world_id,
                        "npc_id": id_map["npc_ids"].get(item.npc_id, item.npc_id),
                        "item_id": item_id,
                    }
                )
            )
    else:
        resolved_inventory_items = seed_npc_inventory(world_id, resolved_npcs, seed, load_staple_catalog_map())

    with db_session(db_path) as conn:
        conn.execute(
            "INSERT INTO worlds (id, prompt, title, seed, status, provider, model_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (world_id, prompt, draft.title, seed, "ready", model.provider, model.model_name, timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO generation_runs (id, world_id, provider, model_name, prompt, started_at, finished_at, latency_ms, error, raw_response) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, world_id, model.provider, model.model_name, prompt, started_at, timestamp, latency_ms, "", raw_response),
        )
        conn.execute(
            "INSERT INTO regions (id, world_id, name, summary, climate, danger_profile) VALUES (?, ?, ?, ?, ?, ?)",
            (id_map["region_id"], world_id, draft.region.name, draft.region.description, "", ""),
        )
        for faction in draft.factions:
            conn.execute(
                "INSERT INTO factions (id, world_id, name, type, goals, public_reputation, power_level, home_place_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_map["faction_ids"][faction.ref],
                    world_id,
                    faction.name,
                    faction.type,
                    faction.goals,
                    faction.public_reputation,
                    faction.power_level,
                    id_map["place_ids"].get(faction.home_place_ref),
                ),
            )
        for place in draft.places:
            conn.execute(
                "INSERT INTO places (id, world_id, region_id, parent_place_id, name, place_type, summary, x, y, terrain, danger_level, population_estimate, controlling_faction_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_map["place_ids"][place.ref],
                    world_id,
                    id_map["region_id"],
                    id_map["place_ids"].get(place.parent_place_ref),
                    place.name,
                    place.place_type,
                    place.summary,
                    place.x,
                    place.y,
                    place.terrain,
                    place.danger_level,
                    place.population_estimate,
                    id_map["faction_ids"].get(place.controlling_faction_ref),
                ),
            )
        for npc in draft.npcs:
            conn.execute(
                "INSERT INTO npcs (id, world_id, name, age, personality, job, faction_id, home_place_id, current_place_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_map["npc_ids"][npc.ref],
                    world_id,
                    npc.name,
                    npc.age,
                    json.dumps(npc.personality),
                    npc.job,
                    id_map["faction_ids"].get(npc.faction_ref),
                    id_map["place_ids"][npc.home_place_ref],
                    id_map["place_ids"][npc.current_place_ref],
                    npc.status,
                ),
            )
        for rel in draft.relationships:
            conn.execute(
                "INSERT INTO relationships (id, world_id, source_type, source_id, target_type, target_id, relation_type, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_map["relationship_ids"][rel.ref],
                    world_id,
                    rel.source_type,
                    {"place": id_map["place_ids"], "faction": id_map["faction_ids"], "npc": id_map["npc_ids"]}[rel.source_type][rel.source_ref],
                    rel.target_type,
                    {"place": id_map["place_ids"], "faction": id_map["faction_ids"], "npc": id_map["npc_ids"]}[rel.target_type][rel.target_ref],
                    rel.relation_type,
                    rel.description,
                ),
            )
        for item in world_items or []:
            conn.execute(
                "INSERT INTO world_items (id, world_id, name, category, rarity, summary, tags_json, value, weight, stackable, consumable, equip_slot, effect_summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_map["world_item_ids"][item.ref],
                    world_id,
                    item.name,
                    item.category,
                    item.rarity,
                    item.summary,
                    json.dumps(item.tags),
                    item.value,
                    item.weight,
                    int(item.stackable),
                    int(item.consumable),
                    item.equip_slot,
                    item.effect_summary,
                ),
            )
        for item in resolved_inventory_items:
            conn.execute(
                "INSERT INTO npc_inventory_items (id, world_id, npc_id, item_source_type, item_id, quantity, condition, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item.id, world_id, item.npc_id, item.item_source_type, item.item_id, item.quantity, item.condition, item.note),
            )

    _write_lore(world_id, draft, id_map, world_items, worlds_path)
    return world_id


async def generate_and_insert_world(prompt: str, model: ConfiguredModel) -> str:
    started = perf_counter()
    try:
        draft, raw_response, provider_latency = await build_world_draft(prompt, model)
        latency_ms = provider_latency or int((perf_counter() - started) * 1000)
        return insert_world(prompt, model, draft, raw_response, latency_ms)
    except (ValidationError, ProviderError, ValueError):
        raise
