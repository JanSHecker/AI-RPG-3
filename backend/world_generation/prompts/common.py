import json
from typing import Any, Optional

from world_generation.schemas import FACTION_COUNT, NPC_COUNT, PERSONALITIES, PLACE_COUNT, RELATIONSHIP_TARGET_COUNT, SECONDARY_RELATIONSHIP_TYPES

def render_json_block(value: Any) -> str:
    return json.dumps(value, indent=2)


def feedback_block(previous_error: Optional[str], previous_response: Optional[str]) -> str:
    if not previous_error:
        return ""
    return (
        f"- Previous validation error: {previous_error[:2000]}\n"
        f"- Previous response excerpt:\n{(previous_response or '')[:2000]}\n"
        "- Retry instruction: Fix the JSON so it exactly matches the requested schema and constraints. "
        "Apply the previous validation error as a mandatory correction list; when it names a specific item, ref, field, "
        "or invalid catalog value, change that exact value in the retry instead of making unrelated changes."
    )


def generation_shape() -> dict[str, int]:
    return {
        "places": PLACE_COUNT,
        "factions": FACTION_COUNT,
        "npcs": NPC_COUNT,
        "relationships": RELATIONSHIP_TARGET_COUNT,
    }


def region_shape() -> dict[str, Any]:
    return {
        "name": "string",
        "summary": "one short regional summary for database/API listings",
        "identity": {
            "overview": "region-wide premise and identity",
            "geography": "major landforms, settlement pattern, and travel assumptions",
            "climate": "weather, seasons, and environmental pressures",
            "peoples_and_culture": "broad cultural assumptions and everyday life",
            "power_centers": "high-level authorities, institutions, and influence blocs",
            "current_conflicts": "broad tensions that later generation can localize",
            "tone_and_themes": "genre tone, recurring motifs, and emotional texture",
            "generation_boundaries": "what later generators should avoid placing in the region primer",
        },
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
                "relation_type": SECONDARY_RELATIONSHIP_TYPES[0],
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
        "personality": PERSONALITIES[:3],
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
        "relation_type": SECONDARY_RELATIONSHIP_TYPES[0],
        "description": "string",
    }
