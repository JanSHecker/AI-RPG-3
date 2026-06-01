import json
from typing import Any, Optional

from world_generation.schemas import FACTION_COUNT, NPC_COUNT, PLACE_COUNT, RELATIONSHIP_COUNT

def render_json_block(value: Any) -> str:
    return json.dumps(value, indent=2)


def feedback_block(previous_error: Optional[str], previous_response: Optional[str]) -> str:
    if not previous_error:
        return ""
    return (
        f"- Previous validation error: {previous_error[:2000]}\n"
        f"- Previous response excerpt:\n{(previous_response or '')[:2000]}\n"
        "- Retry instruction: Fix the JSON so it exactly matches the requested schema and constraints."
    )


def generation_shape() -> dict[str, int]:
    return {
        "places": PLACE_COUNT,
        "factions": FACTION_COUNT,
        "npcs": NPC_COUNT,
        "relationships": RELATIONSHIP_COUNT,
    }


def region_shape() -> dict[str, Any]:
    return {
        "name": "string",
        "description": "string",
    }


def place_shape() -> dict[str, Any]:
    return {
        "ref": "place-kebab-case",
        "name": "string",
        "place_type": "town",
        "summary": "string",
        "x": 50,
        "y": 50,
        "terrain": "hills",
        "danger_level": 3,
        "population_estimate": 1000,
        "controlling_faction_ref": None,
        "parent_place_ref": None,
        "lore": "# Place Name\n\nMarkdown lore.",
    }


def faction_shape() -> dict[str, Any]:
    return {
        "ref": "faction-kebab-case",
        "name": "string",
        "type": "string",
        "goals": "string",
        "public_reputation": "string",
        "power_level": 3,
        "home_place_ref": None,
        "required_places": [
            {
                "name": "string",
                "description": "short description of a place this faction requires later",
            }
        ],
        "required_characters": [
            {
                "name": "string",
                "description": "short description of a character this faction requires later",
            }
        ],
        "requirement_relationships": [
            {
                "source_kind": "place",
                "source_name": "string",
                "target_kind": "character",
                "target_name": "string",
                "relation_type": "string",
                "description": "string",
            }
        ],
        "lore": "# Faction Name\n\nMarkdown lore.",
    }


def npc_shape() -> dict[str, Any]:
    return {
        "ref": "npc-001-kebab-case",
        "name": "string",
        "age": 30,
        "personality": "wary but generous",
        "job": "warden",
        "faction_ref": "faction-kebab-case",
        "home_place_ref": "place-kebab-case",
        "current_place_ref": "place-kebab-case",
        "status": "active",
        "lore": "# NPC Name\n\nMarkdown lore.",
    }


def relationship_shape() -> dict[str, Any]:
    return {
        "ref": "rel-kebab-case",
        "source_type": "faction",
        "source_ref": "faction-kebab-case",
        "target_type": "place",
        "target_ref": "place-kebab-case",
        "relation_type": "alliance",
        "description": "string",
    }
