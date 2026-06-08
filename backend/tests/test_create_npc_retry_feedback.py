import pytest

from world_generation.prompts.common import feedback_block
from world_generation.prompts.create_npc import _validate_npc_batch
from world_generation.schemas import CharacterSlotDraft, FactionDraft, NpcDraft


def test_retry_feedback_treats_previous_error_as_mandatory_correction():
    text = feedback_block(
        "NPC npc-mill-warden has invalid personality value(s) ['calculating'].",
        '{"npcs": []}',
    )

    assert "Previous validation error" in text
    assert "mandatory correction list" in text
    assert "change that exact value" in text


def test_npc_batch_validation_names_invalid_personality_to_change():
    planned_slot = CharacterSlotDraft(
        ref="npc-mill-warden",
        home_place_ref="place-mill",
        current_place_ref="place-mill",
        faction_ref=None,
        age_band="adult",
        role_hint="miller",
        cluster_ref="cluster-mill",
    )
    npc = NpcDraft.model_construct(
        ref="npc-mill-warden",
        name="Mill Warden",
        age=40,
        personality=["patient", "reserved", "calculating"],
        job="miller",
        faction_ref=None,
        home_place_ref="place-mill",
        current_place_ref="place-mill",
        status="active",
        lore="# Mill Warden",
    )
    parsed = type("ParsedNpcBatch", (), {"npcs": [npc]})()

    with pytest.raises(ValueError) as exc_info:
        _validate_npc_batch(parsed, [planned_slot], factions=[])

    text = str(exc_info.value)
    assert "npc-mill-warden" in text
    assert "calculating" in text
    assert "Change those exact invalid value" in text
    assert "exact allowed personality catalog value" in text
