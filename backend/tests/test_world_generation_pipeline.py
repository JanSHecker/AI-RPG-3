import asyncio
import json
from types import SimpleNamespace

import pytest
from model_catalog import ConfiguredModel
from world_generation import item_specialist
from world_generation.agent_workflows import AgentFrameworkChatAdapter, build_world_draft
from world_generation.schemas import (
    DUNGEON_LOCATION_COUNT,
    FACTION_COUNT,
    FACTION_LOCATION_COUNT,
    FactionDraft,
    LocationPlanBatch,
    LocationPlanSlot,
    LocationPlanStep,
    NEUTRAL_VILLAGE_COUNT,
    NPC_COUNT,
    NpcDraft,
    PLACE_COUNT,
    PLACE_TYPES,
    PlaceDraft,
    RegionDraft,
    RelationshipDraft,
    WorldDraft,
    WorldItemDraft,
)


def sample_model() -> ConfiguredModel:
    return ConfiguredModel(id="lmstudio:local-model", label="LM Studio", provider="lmstudio", model_name="local-model")


def sample_world_draft() -> WorldDraft:
    places = [
        PlaceDraft(
            ref=f"place-{idx + 1}",
            name=f"Place {idx + 1}",
            place_type=PLACE_TYPES[idx % len(PLACE_TYPES)],
            summary=f"Summary for place {idx + 1}",
            x=(idx * 7) % 101,
            y=(idx * 11) % 101,
            terrain="hills",
            danger_level=(idx % 5) + 1,
            population_estimate=100 + idx,
            controlling_faction_ref=f"faction-{(idx // FACTION_LOCATION_COUNT) + 1}" if idx < FACTION_COUNT * FACTION_LOCATION_COUNT else None,
            parent_place_ref=None,
            lore=f"Place lore {idx + 1}",
        )
        for idx in range(PLACE_COUNT)
    ]
    factions = [
        FactionDraft(
            ref=f"faction-{idx + 1}",
            name=f"Faction {idx + 1}",
            type="council",
            goals="Hold the road",
            public_reputation="steady",
            power_level=(idx % 5) + 1,
            home_place_ref=None,
            required_places=[
                {
                    "name": f"Faction {idx + 1} Hall",
                    "description": f"A required home base for faction {idx + 1}.",
                }
            ],
            required_characters=[
                {
                    "name": f"Faction {idx + 1} Envoy",
                    "description": f"A required representative for faction {idx + 1}.",
                }
            ],
            requirement_relationships=[
                {
                    "source_kind": "place",
                    "source_name": f"Faction {idx + 1} Hall",
                    "target_kind": "character",
                    "target_name": f"Faction {idx + 1} Envoy",
                    "relation_type": "base of operations",
                    "description": f"The envoy operates from the faction {idx + 1} hall.",
                }
            ],
            lore=f"Faction lore {idx + 1}",
        )
        for idx in range(FACTION_COUNT)
    ]
    npcs = [
        NpcDraft(
            ref=f"npc-{idx + 1}",
            name=f"NPC {idx + 1}",
            age=20 + idx,
            personality="wary but generous",
            job="warden",
            faction_ref=factions[idx % FACTION_COUNT].ref if idx % 3 else None,
            home_place_ref=places[idx % PLACE_COUNT].ref,
            current_place_ref=places[(idx + 1) % PLACE_COUNT].ref,
            status="active",
            lore=f"NPC lore {idx + 1}",
        )
        for idx in range(NPC_COUNT)
    ]
    relationships = [
        RelationshipDraft(
            ref=f"rel-{idx + 1}",
            source_type="npc" if idx >= 4 else "faction",
            source_ref=npcs[idx].ref if idx >= 4 else factions[idx].ref,
            target_type="place" if idx >= 4 else "faction",
            target_ref=npcs[idx].current_place_ref if idx >= 4 else factions[(idx + 1) % FACTION_COUNT].ref,
            relation_type="local tie" if idx >= 4 else "rivalry",
            description=f"Relationship {idx + 1}",
        )
        for idx in range(16)
    ]
    return WorldDraft(
        title="Test Frontier",
        region=RegionDraft(
            name="Test Frontier",
            description="A rough frontier.",
        ),
        places=places,
        factions=factions,
        npcs=npcs,
        relationships=relationships,
    )


def sample_location_plan(world: WorldDraft) -> LocationPlanStep:
    batches = []
    offset = 0
    for faction_idx, faction in enumerate(world.factions):
        batch_places = world.places[offset : offset + FACTION_LOCATION_COUNT]
        offset += FACTION_LOCATION_COUNT
        slots = [
            LocationPlanSlot(
                ref=place.ref,
                place_type=place.place_type,
                x=place.x,
                y=place.y,
                cluster_id=f"cluster-{faction.ref}",
                cluster_kind="faction",
                faction_ref=faction.ref,
                terrain_hint=place.terrain,
                danger_level_hint=place.danger_level,
                population_hint=place.population_estimate,
                purpose="Faction site",
                theme=faction.name,
            )
            for place in batch_places
        ]
        batches.append(
            LocationPlanBatch(
                batch_id=f"batch-faction-{faction_idx + 1:02d}",
                batch_kind="faction_cluster",
                faction_ref=faction.ref,
                center_x=batch_places[0].x,
                center_y=batch_places[0].y,
                slots=slots,
            )
        )
    for batch_id, batch_kind, count in [
        ("batch-neutral-villages", "neutral_villages", NEUTRAL_VILLAGE_COUNT),
        ("batch-dangerous-sites", "dangerous_sites", DUNGEON_LOCATION_COUNT),
    ]:
        batch_places = world.places[offset : offset + count]
        offset += count
        slots = [
            LocationPlanSlot(
                ref=place.ref,
                place_type=place.place_type,
                x=place.x,
                y=place.y,
                cluster_id=batch_id.replace("batch", "cluster"),
                cluster_kind="neutral" if batch_kind == "neutral_villages" else "dangerous",
                faction_ref=None,
                terrain_hint=place.terrain,
                danger_level_hint=place.danger_level,
                population_hint=place.population_estimate,
                purpose="Planned site",
                theme=batch_kind,
            )
            for place in batch_places
        ]
        batches.append(
            LocationPlanBatch(
                batch_id=batch_id,
                batch_kind=batch_kind,
                center_x=batch_places[0].x,
                center_y=batch_places[0].y,
                slots=slots,
            )
        )
    return LocationPlanStep(batches=batches, slots=[slot for batch in batches for slot in batch.slots])


def test_build_world_draft_retries_and_preserves_feedback(monkeypatch):
    from world_generation import agent_workflows as workflows
    from world_generation.step_runtime import StepTranscript, step_label

    prompt_calls = {"region": []}
    sample_world = sample_world_draft()
    plan = sample_location_plan(sample_world)
    region_call_count = 0

    async def fake_chat_completion(model, messages, temperature=None, response_format=None):
        nonlocal region_call_count
        content = messages[-1]["content"]
        if content == "Frontier":
            region_call_count += 1
            if region_call_count == 1:
                return ("not json", 5)
            return (json.dumps({"title": sample_world.title, "region": sample_world.region.model_dump()}), 7)
        if content == "factions":
            return (json.dumps({"factions": [faction.model_dump() for faction in sample_world.factions]}), 13)
        if content == "relationships":
            return (json.dumps({"relationships": [rel.model_dump() for rel in sample_world.relationships]}), 19)

        primary_place = next(
            place
            for place in sorted(sample_world.places, key=lambda candidate: len(candidate.ref), reverse=True)
            if f"home_place_ref must always be {place.ref}" in content
        )
        batch_npcs = [
            npc.model_copy(update={"current_place_ref": primary_place.ref})
            for npc in sample_world.npcs
            if npc.home_place_ref == primary_place.ref
        ]
        return (json.dumps({"npcs": [npc.model_dump() for npc in batch_npcs]}), 17)

    def region_messages(prompt, previous_error=None, previous_response=None):
        prompt_calls["region"].append((previous_error, previous_response))
        return [{"role": "user", "content": prompt}]

    async def fake_generate_place_batch(state, batch):
        refs = {slot.ref for slot in batch.slots}
        places = [place for place in sample_world.places if place.ref in refs]
        return batch, places, StepTranscript(
            name=f"places_{batch.batch_id.replace('-', '_')}",
            label=step_label("villages_places"),
            status="done",
            latency_ms=11,
            parsed_payload={"places": [place.model_dump() for place in places]},
        )

    monkeypatch.setattr(workflows, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(workflows.create_region, "build_messages", region_messages)
    monkeypatch.setattr(workflows.create_faction, "build_messages", lambda *args: [{"role": "user", "content": "factions"}])
    monkeypatch.setattr(workflows.create_relationships, "build_messages", lambda *args: [{"role": "user", "content": "relationships"}])
    monkeypatch.setattr(workflows.create_location_plan, "build_location_plan", lambda *args: plan)
    monkeypatch.setattr(workflows.create_village, "_generate_batch", fake_generate_place_batch)
    monkeypatch.setattr(
        workflows.create_npc,
        "_distribute_npc_counts",
        lambda places: {place.ref: len([npc for npc in sample_world.npcs if npc.home_place_ref == place.ref]) for place in places},
    )

    draft, raw_response, latency_ms = asyncio.run(build_world_draft("Frontier", sample_model()))

    assert draft.title == "Test Frontier"
    assert latency_ms >= 0
    assert len(prompt_calls["region"]) == 2
    assert "JSON object" in prompt_calls["region"][1][0]
    assert prompt_calls["region"][1][1] == "not json"

    payload = json.loads(raw_response)
    assert payload["pipeline_version"] == "agent-framework-v1"
    assert [step["name"] for step in payload["steps"]] == [
        "region",
        "factions",
        "location_plan",
        "villages_places",
        "npcs",
        "relationships",
    ]
    assert payload["location_plan"]["slots"][0]["ref"] == sample_world.places[0].ref
    assert payload["steps"][0]["attempts"][0]["status"] == "failed"
    assert payload["steps"][0]["attempts"][1]["status"] == "done"


def test_faction_prompt_runs_before_places_and_requires_planning_notes():
    from world_generation.prompts import create_faction

    messages = create_faction.build_messages(
        "A frontier under a broken road",
        RegionDraft(name="Ash Road", description="A contested road frontier."),
    )
    content = messages[-1]["content"]

    assert "Places:" not in content
    assert "home_place_ref must always be null" in content
    assert "required_places" in content
    assert "required_characters" in content
    assert "source_name and target_name must exactly match names" in content


def test_location_plan_is_stable_clustered_and_counted():
    from world_generation.prompts import create_location_plan

    world = sample_world_draft()
    plan = create_location_plan.build_location_plan("A frontier under a broken road", world.region, world.factions)
    repeated = create_location_plan.build_location_plan("A frontier under a broken road", world.region, world.factions)

    assert plan.model_dump() == repeated.model_dump()
    assert len(plan.slots) == PLACE_COUNT
    assert len(plan.batches) == FACTION_COUNT + 2
    assert sum(1 for slot in plan.slots if slot.cluster_kind == "faction") == FACTION_COUNT * FACTION_LOCATION_COUNT
    assert sum(1 for slot in plan.slots if slot.cluster_kind == "neutral") == NEUTRAL_VILLAGE_COUNT
    assert sum(1 for slot in plan.slots if slot.cluster_kind == "dangerous") == DUNGEON_LOCATION_COUNT
    assert all(slot.faction_ref is None for slot in plan.slots if slot.cluster_kind in {"neutral", "dangerous"})
    for batch in plan.batches:
        if batch.batch_kind == "faction_cluster":
            assert len(batch.slots) == FACTION_LOCATION_COUNT
            assert all(abs(slot.x - batch.center_x) <= 13 and abs(slot.y - batch.center_y) <= 13 for slot in batch.slots)


def test_place_generation_runs_one_parallel_batch_per_plan_batch(monkeypatch):
    from world_generation.prompts import create_village
    from world_generation.step_runtime import StepTranscript

    world = sample_world_draft()
    plan = sample_location_plan(world)
    calls = []
    updates = []

    async def fake_generate_batch(state, batch):
        calls.append(batch.batch_id)
        await state.updater(
            f"places_{batch.batch_id.replace('-', '_')}",
            "running",
            {"attempts": 1, "label": create_village._batch_label(batch, state.factions_step.factions)},
        )
        refs = {slot.ref for slot in batch.slots}
        places = [place for place in world.places if place.ref in refs]
        return batch, places, StepTranscript(name=batch.batch_id, label=batch.batch_id, status="done", parsed_payload={})

    async def updater(step_name, status, payload):
        updates.append((step_name, status, payload))

    monkeypatch.setattr(create_village, "_generate_batch", fake_generate_batch)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        updater=updater,
        step_transcripts=[],
        total_latency_ms=0,
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        location_plan_step=plan,
        places_step=None,
    )

    result = asyncio.run(create_village.run_step(state))

    assert calls == [batch.batch_id for batch in plan.batches]
    assert updates[1][2]["label"] == f"{world.factions[0].name} Locations"
    assert [place.ref for place in result.places_step.places] == [slot.ref for slot in plan.slots]
    assert result.step_transcripts[-1].name == "villages_places"


def test_place_generation_rejects_duplicate_or_missing_plan_refs(monkeypatch):
    from providers import ProviderError
    from world_generation.prompts import create_village
    from world_generation.step_runtime import StepTranscript

    world = sample_world_draft()
    plan = sample_location_plan(world)

    async def fake_generate_batch(state, batch):
        refs = {slot.ref for slot in batch.slots}
        places = [place for place in world.places if place.ref in refs]
        if batch == plan.batches[0]:
            places = [places[0], *places[:-1]]
        return batch, places, StepTranscript(name=batch.batch_id, label=batch.batch_id, status="done", parsed_payload={})

    monkeypatch.setattr(create_village, "_generate_batch", fake_generate_batch)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        updater=None,
        step_transcripts=[],
        total_latency_ms=0,
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        location_plan_step=plan,
        places_step=None,
    )

    with pytest.raises(ProviderError):
        asyncio.run(create_village.run_step(state))


def test_npc_generation_retries_unknown_faction_ref(monkeypatch):
    from world_generation import step_runtime
    from world_generation.prompts import create_npc

    world = sample_world_draft()
    place = world.places[0]
    invalid_npc = world.npcs[0].model_copy(
        update={
            "ref": f"npc-{place.ref.removeprefix('place-')}-florian",
            "faction_ref": "golden-court",
            "home_place_ref": place.ref,
            "current_place_ref": place.ref,
        }
    )
    valid_npc = invalid_npc.model_copy(update={"faction_ref": None})
    calls = []

    async def fake_complete_json(*, model, step_name, schema, messages):
        calls.append(messages[-1]["content"])
        npc = invalid_npc if len(calls) == 1 else valid_npc
        return (json.dumps({"npcs": [npc.model_dump()]}), 5)

    monkeypatch.setattr(step_runtime.CHAT_ADAPTER, "complete_json", fake_complete_json)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        places_step=SimpleNamespace(places=world.places),
    )

    npcs, transcript = asyncio.run(create_npc._generate_place_batch(state, place, 1))

    assert npcs[0].faction_ref is None
    assert len(calls) == 2
    assert "golden-court" in calls[1]
    assert "must be null or one of" in calls[1]
    assert transcript.attempts[0].status == "failed"
    assert transcript.attempts[1].status == "done"


def test_npc_generation_records_one_parallel_batch_per_place(monkeypatch):
    from world_generation.prompts import create_npc
    from world_generation.step_runtime import StepTranscript

    world = sample_world_draft()
    calls = []
    updates = []

    async def fake_generate_place_batch(state, place, batch_size):
        calls.append((place.ref, batch_size))
        await state.updater(
            f"npcs_{place.ref.replace('-', '_')}",
            "running",
            {"attempts": 1, "label": create_npc._batch_label(place, batch_size)},
        )
        batch_npcs = [
            npc.model_copy(update={"current_place_ref": place.ref})
            for npc in world.npcs
            if npc.home_place_ref == place.ref
        ]
        return batch_npcs, StepTranscript(
            name=f"npcs_{place.ref.replace('-', '_')}",
            label=create_npc._batch_label(place, batch_size),
            status="done",
            parsed_payload={"npcs": [npc.model_dump() for npc in batch_npcs]},
        )

    async def updater(step_name, status, payload):
        updates.append((step_name, status, payload))

    counts_by_place = {
        place.ref: len([npc for npc in world.npcs if npc.home_place_ref == place.ref])
        for place in world.places
    }
    monkeypatch.setattr(create_npc, "_distribute_npc_counts", lambda places: counts_by_place)
    monkeypatch.setattr(create_npc, "_generate_place_batch", fake_generate_place_batch)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        updater=updater,
        step_transcripts=[],
        total_latency_ms=0,
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        places_step=SimpleNamespace(places=world.places),
        npc_step=None,
    )

    result = asyncio.run(create_npc.run_step(state))

    assert calls == [(place.ref, counts_by_place[place.ref]) for place in world.places]
    assert updates[0] == ("npcs", "running", {"attempts": 0, "error": ""})
    assert updates[1][0] == f"npcs_{world.places[0].ref.replace('-', '_')}"
    assert updates[1][2]["label"] == f"{world.places[0].name} NPCs"
    assert len(result.npc_step.npcs) == NPC_COUNT
    assert result.step_transcripts[-1].name == "npcs"


def test_build_world_items_draft_uses_workflow_runtime(monkeypatch):
    from world_generation import agent_workflows as workflows

    captured = {}
    world = sample_world_draft()
    scaffold = [
        WorldItemDraft(
            ref="item-ember-key",
            name="Ember Key",
            category="trinket",
            rarity="rare",
            summary="A key from the old watchtowers.",
            tags=["quest"],
            value=120,
            weight=0.2,
            stackable=False,
            consumable=False,
            equip_slot=None,
            effect_summary="Opens one forgotten lock.",
            lore="Item lore",
        )
    ]

    async def fake_chat_completion(model, messages, temperature=None, response_format=None):
        return (json.dumps({"world_items": [item.model_dump() for item in scaffold]}), 9)

    def items_messages(prompt, world, scaffold, previous_error=None, previous_response=None):
        captured["previous_error"] = previous_error
        captured["previous_response"] = previous_response
        return [{"role": "user", "content": prompt}]

    monkeypatch.setattr(workflows, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(workflows.create_items, "build_messages", items_messages)

    step, raw_response, latency_ms = asyncio.run(
        item_specialist.build_world_items_draft(
            "Old relics",
            sample_model(),
            world,
            scaffold,
            previous_error="bad schema",
            previous_response="{oops}",
        )
    )

    assert step.world_items[0].ref == "item-ember-key"
    assert latency_ms >= 0
    assert captured == {"previous_error": "bad schema", "previous_response": "{oops}"}
    assert json.loads(raw_response)["steps"][0]["name"] == "world_items"


def test_agent_framework_chat_adapter_uses_strict_schema(monkeypatch):
    from world_generation import agent_workflows as workflows

    captured = {}

    async def fake_chat_completion(model, messages, temperature=None, response_format=None):
        captured["response_format"] = response_format
        return ("{}", 3)

    monkeypatch.setattr(workflows, "chat_completion", fake_chat_completion)

    asyncio.run(
        AgentFrameworkChatAdapter().complete_json(
            model=sample_model(),
            step_name="probe",
            schema=type(
                "ProbeSchema",
                (WorldItemDraft,),
                {},
            ),
            messages=[{"role": "user", "content": "Return JSON."}],
        )
    )

    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["name"] == "probe"
