import json
import shutil
from pathlib import Path
from typing import Any, Optional

from config import settings
from database import db_session
from item_catalog import load_staple_catalog_map


def row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def list_worlds() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, title, prompt, status, provider, model_name, created_at, updated_at FROM worlds ORDER BY created_at DESC"
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def get_world(world_id: str) -> Optional[dict[str, Any]]:
    with db_session() as conn:
        world = conn.execute("SELECT * FROM worlds WHERE id = ?", (world_id,)).fetchone()
        if not world:
            return None
        region = conn.execute("SELECT * FROM regions WHERE world_id = ?", (world_id,)).fetchone()
        data = row_to_dict(world)
        data["region"] = row_to_dict(region)
        return data


def delete_world(world_id: str) -> bool:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM worlds WHERE id = ?", (world_id,))
    if cur.rowcount > 0:
        shutil.rmtree(settings.worlds_path / world_id, ignore_errors=True)
    return cur.rowcount > 0


def list_table(world_id: str, table: str) -> list[dict[str, Any]]:
    allowed = {"places", "npcs", "factions", "relationships", "world_items"}
    if table not in allowed:
        raise ValueError("Unsupported table.")
    with db_session() as conn:
        if table == "relationships":
            query = f"SELECT * FROM {table} WHERE world_id = ? ORDER BY id"
        else:
            query = f"SELECT * FROM {table} WHERE world_id = ? ORDER BY name"
        rows = conn.execute(query, (world_id,)).fetchall()
        items = [row_to_dict(row) for row in rows]
        if table == "world_items":
            for item in items:
                item["tags"] = json.loads(item.pop("tags_json", "[]"))
                item["stackable"] = bool(item["stackable"])
                item["consumable"] = bool(item["consumable"])
        if table == "npcs":
            for item in items:
                try:
                    parsed = json.loads(item["personality"])
                except (TypeError, json.JSONDecodeError):
                    parsed = item["personality"]
                item["personality"] = parsed if isinstance(parsed, list) else [parsed]
        return items


def list_npc_inventory_items(world_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT
                inventory.id,
                inventory.world_id,
                inventory.npc_id,
                npcs.name AS npc_name,
                inventory.item_source_type,
                inventory.item_id,
                inventory.quantity,
                inventory.condition,
                inventory.note
            FROM npc_inventory_items AS inventory
            JOIN npcs ON npcs.id = inventory.npc_id
            WHERE inventory.world_id = ?
            ORDER BY npcs.name, inventory.id
            """,
            (world_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_resolved_items(world_id: str) -> list[dict[str, Any]]:
    staple_map = load_staple_catalog_map()
    world_items = {item["id"]: item for item in list_table(world_id, "world_items")}
    inventory = list_npc_inventory_items(world_id)
    grouped_holders: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in inventory:
        grouped_holders.setdefault((entry["item_source_type"], entry["item_id"]), []).append(entry)

    rows: list[dict[str, Any]] = []

    for (source_type, item_id), holders in grouped_holders.items():
        if source_type == "staple":
            definition = staple_map.get(item_id)
            if not definition:
                continue
            row = definition.model_dump(exclude={"lore_path"})
            row.update(
                {
                    "source_type": "staple",
                    "lore_entity_type": "staple-items",
                    "carrier_count": len(holders),
                    "carriers": holders,
                    "total_quantity": sum(holder["quantity"] for holder in holders),
                }
            )
            rows.append(row)
        elif source_type == "world":
            world_item = world_items.get(item_id)
            if not world_item:
                continue
            row = {
                **world_item,
                "source_type": "world",
                "lore_entity_type": "items",
                "carrier_count": len(holders),
                "carriers": holders,
                "total_quantity": sum(holder["quantity"] for holder in holders),
            }
            rows.append(row)

    carried_world_ids = {row["id"] for row in rows if row["source_type"] == "world"}
    for item_id, world_item in world_items.items():
        if item_id in carried_world_ids:
            continue
        rows.append(
            {
                **world_item,
                "source_type": "world",
                "lore_entity_type": "items",
                "carrier_count": 0,
                "carriers": [],
                "total_quantity": 0,
            }
        )

    return sorted(rows, key=lambda row: (row["source_type"], row["name"]))


def safe_lore_path(world_id: str, entity_type: str, entity_id: str) -> Path:
    root = (settings.worlds_path / world_id).resolve()
    if entity_type == "region":
        target = root / "region.md"
    elif entity_type in {"places", "factions", "npcs", "items"}:
        target = root / entity_type / f"{entity_id}.md"
    elif entity_type == "staple-items":
        target = settings.staple_item_lore_path.resolve() / f"{entity_id}.md"
    else:
        raise ValueError("Unsupported lore entity type.")
    resolved = target.resolve()
    if entity_type == "staple-items":
        staple_root = settings.staple_item_lore_path.resolve()
        if resolved != staple_root and staple_root not in resolved.parents:
            raise ValueError("Invalid lore path.")
        return resolved
    if resolved != root and root not in resolved.parents:
        raise ValueError("Invalid lore path.")
    return resolved


def read_lore(world_id: str, entity_type: str, entity_id: str) -> Optional[str]:
    path = safe_lore_path(world_id, entity_type, entity_id)
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
