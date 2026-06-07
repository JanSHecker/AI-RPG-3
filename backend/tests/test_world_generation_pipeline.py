import asyncio
import json
from types import SimpleNamespace

import pytest
from model_catalog import ConfiguredModel
from world_generation import item_specialist
from world_generation.agent_workflows import AgentFrameworkChatAdapter, build_world_draft
from world_generation.schemas import (
    CharacterClusterDraft,
    CharacterDiagramStep,
    CharacterSegmentDraft,
    CharacterSlotDraft,
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
    PERSONALITIES,
    PLACE_COUNT,
    PLACE_TYPES,
    PlaceDraft,
    PlannedRelationshipDraft,
    RegionDraft,
    RELATIONSHIP_TARGET_COUNT,
    RELATIONSHIP_TYPES,
    RelationshipDraft,
    RelationshipOpportunityDraft,
    WorldDraft,
    WorldItemDraft,
)


def sample_model() -> ConfiguredModel:
    return ConfiguredModel(id="lmstudio:local-model", label="LM Studio", provider="lmstudio", model_name="local-model")


def sample_personalities(idx: int) -> list[str]:
    return [PERSONALITIES[(idx + offset) % len(PERSONALITIES)] for offset in range(3)]


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
            personality=sample_personalities(idx),
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
            relation_type=RELATIONSHIP_TYPES[RELATIONSHIP_TYPES.index("local tie")] if idx >= 4 else RELATIONSHIP_TYPES[RELATIONSHIP_TYPES.index("rivalry")],
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


def age_band_for_age(age: int) -> str:
    if age < 15:
        return "child"
    if age < 20:
        return "teen"
    if age < 30:
        return "young adult"
    if age < 60:
        return "adult"
    return "elder"


def sample_character_diagram(world: WorldDraft) -> CharacterDiagramStep:
    clusters_by_place = {
        place.ref: CharacterClusterDraft(
            ref=f"cluster-{place.ref}",
            kind="household",
            place_ref=place.ref,
            summary=f"Household and social ties in {place.name}.",
        )
        for place in world.places
    }
    slots = [
        CharacterSlotDraft(
            ref=npc.ref,
            home_place_ref=npc.home_place_ref,
            current_place_ref=npc.current_place_ref,
            faction_ref=npc.faction_ref,
            age_band=age_band_for_age(npc.age),
            role_hint=npc.job,
            cluster_ref=clusters_by_place[npc.home_place_ref].ref,
        )
        for npc in world.npcs
    ]
    relationships = [
        PlannedRelationshipDraft(
            ref=f"rel-plan-sibling-{idx // 2 + 1:02d}",
            source_ref=slots[idx].ref,
            target_ref=slots[idx + 1].ref,
            relation_type="sibling",
            description="Planned sibling tie that should shape both characters.",
        )
        for idx in range(0, len(slots), 2)
    ]
    return CharacterDiagramStep(
        clusters=list(clusters_by_place.values()),
        slots=slots,
        relationships=relationships,
    )


def sample_final_relationships(world: WorldDraft, diagram: CharacterDiagramStep) -> list[RelationshipDraft]:
    relationships = [
        RelationshipDraft(
            ref=planned.ref,
            source_type="npc",
            source_ref=planned.source_ref,
            target_type="npc",
            target_ref=planned.target_ref,
            relation_type=planned.relation_type,
            description=planned.description,
        )
        for planned in diagram.relationships
    ]
    idx = 0
    while len(relationships) < RELATIONSHIP_TARGET_COUNT:
        source = world.npcs[idx % len(world.npcs)]
        target = world.places[idx % len(world.places)]
        relationships.append(
            RelationshipDraft(
                ref=f"rel-extra-{idx + 1:03d}",
                source_type="npc",
                source_ref=source.ref,
                target_type="place",
                target_ref=target.ref,
                relation_type="local tie",
                description=f"{source.name} has a local tie to {target.name}.",
            )
        )
        idx += 1
    return relationships


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
    relationship_call_count = 0

    def parse_json_after(content: str, marker: str):
        decoder = json.JSONDecoder()
        start = content.index(marker) + len(marker)
        return decoder.raw_decode(content[start:].lstrip())[0]

    async def fake_chat_completion(model, messages, temperature=None, response_format=None):
        nonlocal region_call_count, relationship_call_count
        content = messages[-1]["content"]
        if content == "Frontier":
            region_call_count += 1
            if region_call_count == 1:
                return ("not json", 5)
            return (json.dumps({"title": sample_world.title, "region": sample_world.region.model_dump()}), 7)
        if content == "factions":
            return (json.dumps({"factions": [faction.model_dump() for faction in sample_world.factions]}), 13)
        if "Required planned relationships:" in content:
            relationship_call_count += 1
            planned = parse_json_after(content, "Required planned relationships:\n")
            batch_npcs = parse_json_after(content, "NPCs:\n")
            batch_places = parse_json_after(content, "Places:\n")
            target_count = int(content.split("Target count:\n", 1)[1].split("\n", 1)[0])
            relationships = [
                RelationshipDraft(
                    ref=relationship["ref"],
                    source_type=relationship["source_type"],
                    source_ref=relationship["source_ref"],
                    target_type=relationship["target_type"],
                    target_ref=relationship["target_ref"],
                    relation_type=relationship["relation_type"],
                    description=relationship["description"],
                )
                for relationship in planned
            ]
            idx = 0
            npc_refs = sorted(
                {npc["ref"] for npc in batch_npcs}
                .union({relationship["source_ref"] for relationship in planned})
                .union({relationship["target_ref"] for relationship in planned})
            )
            place_refs = sorted({place["ref"] for place in batch_places})
            while len(relationships) < target_count:
                source_ref = npc_refs[idx % len(npc_refs)]
                target_ref = place_refs[idx % len(place_refs)]
                relationships.append(
                    RelationshipDraft(
                        ref=f"rel-extra-{relationship_call_count:03d}-{idx + 1:03d}",
                        source_type="npc",
                        source_ref=source_ref,
                        target_type="place",
                        target_ref=target_ref,
                        relation_type="local tie",
                        description=f"{source_ref} has a local tie to {target_ref}.",
                    )
                )
                idx += 1
            return (json.dumps({"relationships": [rel.model_dump() for rel in relationships]}), 19)

        primary_place = next(
            place
            for place in sorted(sample_world.places, key=lambda candidate: len(candidate.ref), reverse=True)
            if f"Primary place:\n{json.dumps(place.model_dump(), indent=2)}" in content
        )
        planned_slots = parse_json_after(content, "Planned character slots for this place:\n")
        batch_npcs = [
            NpcDraft(
                ref=slot["ref"],
                name=f"NPC {slot['ref']}",
                age=slot["age_range"]["min"],
                personality=sample_personalities(idx),
                job="warden",
                faction_ref=slot["faction_ref"],
                home_place_ref=slot["home_place_ref"],
                current_place_ref=slot["current_place_ref"],
                status="active",
                lore=f"NPC lore {slot['ref']} near {primary_place.name}",
            )
            for idx, slot in enumerate(planned_slots)
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
    monkeypatch.setattr(workflows.create_location_plan, "build_location_plan", lambda *args: plan)
    monkeypatch.setattr(workflows.create_village, "_generate_batch", fake_generate_place_batch)

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
        "character_diagram",
        "npcs",
        "relationships",
    ]
    assert payload["location_plan"]["slots"][0]["ref"] == sample_world.places[0].ref
    assert payload["character_diagram"]["slots"][0]["ref"].startswith("npc-slot-")
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


def test_character_diagram_validation_requires_connected_slots():
    from world_generation.prompts import create_character_diagram

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    diagram.relationships = diagram.relationships[:-1]

    with pytest.raises(ValueError, match="Every character slot"):
        create_character_diagram.validate_character_diagram(diagram, world.places, world.factions)


def test_heuristic_character_diagram_is_deterministic_primary_and_segmented():
    from world_generation.prompts import create_character_diagram
    from world_generation.schemas import PRIMARY_RELATIONSHIP_TYPES, SECONDARY_RELATIONSHIP_TYPES

    world = sample_world_draft()
    first, first_opportunities, first_segments = create_character_diagram.build_character_diagram(
        "Frontier",
        world.region,
        world.places,
        world.factions,
    )
    second, second_opportunities, second_segments = create_character_diagram.build_character_diagram(
        "Frontier",
        world.region,
        world.places,
        world.factions,
    )

    assert first.model_dump() == second.model_dump()
    assert [opportunity.model_dump() for opportunity in first_opportunities] == [opportunity.model_dump() for opportunity in second_opportunities]
    assert [segment.model_dump() for segment in first_segments] == [segment.model_dump() for segment in second_segments]
    assert len(first.slots) == NPC_COUNT
    assert all(relationship.relation_type in PRIMARY_RELATIONSHIP_TYPES for relationship in first.relationships)
    assert not any(relationship.relation_type in SECONDARY_RELATIONSHIP_TYPES for relationship in first.relationships)
    assert all(relationship.description == create_character_diagram.STRUCTURAL_DESCRIPTION for relationship in first.relationships)

    marriage_bridges = [relationship for relationship in first.relationships if "marriage-bridge" in relationship.ref]
    assert marriage_bridges
    slots_by_ref = {slot.ref: slot for slot in first.slots}
    assert any(slots_by_ref[relationship.source_ref].cluster_ref != slots_by_ref[relationship.target_ref].cluster_ref for relationship in marriage_bridges)

    segmented_refs = [slot_ref for segment in first_segments for slot_ref in segment.slot_refs]
    assert sorted(segmented_refs) == sorted(slot.ref for slot in first.slots)
    assert len(segmented_refs) == len(set(segmented_refs))
    assert create_character_diagram.MAX_NPC_BATCH_SIZE == 4
    assert all(len(segment.slot_refs) <= create_character_diagram.MAX_NPC_BATCH_SIZE for segment in first_segments)


def test_heuristic_character_diagram_noise_creates_context_not_relationships():
    from world_generation.prompts import create_character_diagram

    world = sample_world_draft()
    diagram, opportunities, segments = create_character_diagram.build_character_diagram(
        "Frontier",
        world.region,
        world.places,
        world.factions,
    )

    assert any(slot.current_place_ref != slot.home_place_ref for slot in diagram.slots)
    assert any(opportunity.kind == "moved_away" for opportunity in opportunities)
    assert any(opportunity.kind in {"same_faction", "faction_mismatch", "marriage_bridge"} for opportunity in opportunities)
    moved_refs = {opportunity.slot_refs[0] for opportunity in opportunities if opportunity.kind == "moved_away"}
    assert moved_refs.issubset({slot.ref for slot in diagram.slots})
    assert segments


def test_relationship_prompt_uses_opportunities_as_secondary_context():
    from world_generation.prompts import create_relationships

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    opportunity = RelationshipOpportunityDraft(
        ref="opp-moved-away-001",
        kind="moved_away",
        slot_refs=[world.npcs[0].ref],
        place_refs=[world.npcs[0].home_place_ref, world.npcs[0].current_place_ref],
        summary="This is context only.",
    )
    unrelated = RelationshipOpportunityDraft(
        ref="opp-unrelated-001",
        kind="moved_away",
        slot_refs=[world.npcs[-1].ref],
        place_refs=[],
        summary="This unrelated context should be filtered out.",
    )
    segment = CharacterSegmentDraft(
        ref="segment-focused",
        cluster_refs=[diagram.slots[0].cluster_ref],
        slot_refs=[world.npcs[0].ref, world.npcs[1].ref],
        summary="Focused relationship segment.",
    )
    batches = create_relationships._build_relationship_batches(
        segments=[segment],
        places=world.places,
        factions=world.factions,
        npcs=world.npcs,
        planned_relationships=[
            PlannedRelationshipDraft(
                ref="rel-plan-parent-001",
                source_ref=world.npcs[1].ref,
                target_ref=world.npcs[0].ref,
                relation_type="parent",
                description="Structural heritage tie.",
            )
        ],
        relationship_opportunities=[opportunity, unrelated],
        target_count=4,
    )
    batch = batches[0]
    messages = create_relationships.build_messages(
        "Frontier",
        world.region,
        batch.places,
        batch.factions,
        batch.npcs,
        batch.planned_relationships,
        batch.relationship_opportunities,
        batch.target_count,
    )
    content = messages[-1]["content"]
    outside_place = next(place for place in world.places if place.ref not in {batch_place.ref for batch_place in batch.places})

    assert "Secondary relationship opportunities" in content
    assert "Relationship opportunities are not canon yet" in content
    assert "Create secondary relationships from the completed NPC lore" in content
    assert opportunity.ref in content
    assert unrelated.ref not in content
    assert world.npcs[-1].ref not in content
    assert outside_place.ref not in content


def test_final_relationship_validation_requires_planned_relationships():
    from world_generation.prompts import create_relationships

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    final_relationships = sample_final_relationships(world, diagram)
    parsed = create_relationships.RelationshipsStep(relationships=final_relationships[1:])

    with pytest.raises(ValueError, match="must include planned relationship"):
        create_relationships._validate_relationships(parsed, world.places, world.factions, world.npcs, diagram.relationships)


def test_relationship_generation_runs_parallel_batches_and_merges(monkeypatch):
    from world_generation.prompts import create_relationships
    from world_generation.step_runtime import StepTranscript

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    segments = [
        CharacterSegmentDraft(
            ref="segment-first",
            cluster_refs=[diagram.slots[0].cluster_ref],
            slot_refs=[slot.ref for slot in diagram.slots[:30]],
            summary="First half.",
        ),
        CharacterSegmentDraft(
            ref="segment-second",
            cluster_refs=[diagram.slots[30].cluster_ref],
            slot_refs=[slot.ref for slot in diagram.slots[30:]],
            summary="Second half.",
        ),
    ]
    calls = []

    async def fake_generate_relationship_batch(state, batch):
        calls.append((batch.ref, batch.target_count, [relationship.ref for relationship in batch.planned_relationships]))
        relationships = [
            RelationshipDraft(
                ref=planned.ref,
                source_type="npc",
                source_ref=planned.source_ref,
                target_type="npc",
                target_ref=planned.target_ref,
                relation_type=planned.relation_type,
                description=planned.description,
            )
            for planned in batch.planned_relationships
        ]
        idx = 0
        while len(relationships) < batch.target_count:
            npc = batch.npcs[idx % len(batch.npcs)]
            place = batch.places[idx % len(batch.places)]
            relationships.append(
                RelationshipDraft(
                    ref=f"rel-extra-{batch.ref.replace(':', '-')}-{idx + 1:03d}",
                    source_type="npc",
                    source_ref=npc.ref,
                    target_type="place",
                    target_ref=place.ref,
                    relation_type="local tie",
                    description=f"{npc.ref} is locally tied to {place.ref}.",
                )
            )
            idx += 1
        return batch, relationships, StepTranscript(
            name=batch.step_name,
            label=batch.label,
            status="done",
            latency_ms=3,
            parsed_payload={"relationships": [relationship.model_dump() for relationship in relationships]},
        )

    monkeypatch.setattr(create_relationships, "_generate_relationship_batch", fake_generate_relationship_batch)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        updater=None,
        step_transcripts=[],
        total_latency_ms=0,
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        places_step=SimpleNamespace(places=world.places),
        character_diagram_step=diagram,
        character_segments=segments,
        relationship_opportunities=[],
        npc_step=SimpleNamespace(npcs=world.npcs),
        relationships_step=None,
    )

    result = asyncio.run(create_relationships.run_step(state))

    assert len(calls) > 1
    assert sum(target_count for _, target_count, _ in calls) == RELATIONSHIP_TARGET_COUNT
    assert sorted(ref for _, _, refs in calls for ref in refs) == sorted(relationship.ref for relationship in diagram.relationships)
    assert len(result.relationships_step.relationships) == RELATIONSHIP_TARGET_COUNT
    assert result.step_transcripts[-1].name == "relationships"


def test_final_relationship_validation_rejects_duplicate_refs():
    from world_generation.prompts import create_relationships

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    final_relationships = sample_final_relationships(world, diagram)
    final_relationships[1] = final_relationships[1].model_copy(update={"ref": final_relationships[0].ref})
    parsed = create_relationships.RelationshipsStep(relationships=final_relationships)

    with pytest.raises(ValueError, match="duplicate ref"):
        create_relationships._validate_relationships(parsed, world.places, world.factions, world.npcs, diagram.relationships)


def test_final_relationship_validation_rejects_invalid_refs():
    from world_generation.prompts import create_relationships

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    final_relationships = sample_final_relationships(world, diagram)
    final_relationships[-1] = final_relationships[-1].model_copy(update={"source_ref": "missing-npc"})
    parsed = create_relationships.RelationshipsStep(relationships=final_relationships)

    with pytest.raises(ValueError, match="source_ref must match"):
        create_relationships._validate_relationships(parsed, world.places, world.factions, world.npcs, diagram.relationships)


def test_final_relationship_validation_rejects_planned_relationship_mutation():
    from world_generation.prompts import create_relationships

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    final_relationships = sample_final_relationships(world, diagram)
    final_relationships[0] = final_relationships[0].model_copy(update={"relation_type": "local tie"})
    parsed = create_relationships.RelationshipsStep(relationships=final_relationships)

    with pytest.raises(ValueError, match="changed planned relation_type"):
        create_relationships._validate_relationships(parsed, world.places, world.factions, world.npcs, diagram.relationships)


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
    planned_slot = CharacterSlotDraft(
        ref=f"npc-{place.ref.removeprefix('place-')}-florian",
        home_place_ref=place.ref,
        current_place_ref=place.ref,
        faction_ref=None,
        age_band="young adult",
        role_hint="local warden",
        cluster_ref=f"cluster-{place.ref}",
    )
    invalid_npc = world.npcs[0].model_copy(
        update={
            "ref": planned_slot.ref,
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
        character_diagram_step=SimpleNamespace(relationships=[]),
    )

    npcs, transcript = asyncio.run(create_npc._generate_place_batch(state, place, [planned_slot]))

    assert npcs[0].faction_ref is None
    assert len(calls) == 2
    assert "golden-court" in calls[1]
    assert "changed faction_ref" in calls[1]
    assert transcript.attempts[0].status == "failed"
    assert transcript.attempts[1].status == "done"


def test_npc_prompt_uses_numeric_age_range_for_planned_slots():
    from world_generation.prompts import create_npc

    world = sample_world_draft()
    place = world.places[0]
    planned_slot = CharacterSlotDraft(
        ref="npc-planned-adult",
        home_place_ref=place.ref,
        current_place_ref=place.ref,
        faction_ref=None,
        age_band="adult",
        role_hint="local mediator",
        cluster_ref=f"cluster-{place.ref}",
    )

    messages = create_npc.build_messages(
        "Frontier",
        world.region,
        place,
        [place],
        world.factions,
        [planned_slot],
        [],
    )
    content = messages[-1]["content"]

    assert '"age_range": {' in content
    assert '"min": 30' in content
    assert '"max": 59' in content
    assert '"age_band"' not in content
    assert "age must be within the planned slot age_range" in content


def test_npc_generation_clamps_age_to_planned_range(monkeypatch):
    from world_generation import step_runtime
    from world_generation.prompts import create_npc

    world = sample_world_draft()
    place = world.places[0]
    planned_slot = CharacterSlotDraft(
        ref="npc-planned-child",
        home_place_ref=place.ref,
        current_place_ref=place.ref,
        faction_ref=None,
        age_band="child",
        role_hint="younger family member",
        cluster_ref=f"cluster-{place.ref}",
    )
    child_with_elder_age = world.npcs[0].model_copy(
        update={
            "ref": planned_slot.ref,
            "age": 90,
            "faction_ref": None,
            "home_place_ref": place.ref,
            "current_place_ref": place.ref,
        }
    )

    async def fake_complete_json(*, model, step_name, schema, messages):
        return (json.dumps({"npcs": [child_with_elder_age.model_dump()]}), 5)

    monkeypatch.setattr(step_runtime.CHAT_ADAPTER, "complete_json", fake_complete_json)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        places_step=SimpleNamespace(places=world.places),
        character_diagram_step=SimpleNamespace(relationships=[]),
    )

    npcs, transcript = asyncio.run(create_npc._generate_place_batch(state, place, [planned_slot]))

    assert npcs[0].age == 14
    assert transcript.attempts[0].status == "done"


def test_npc_generation_chunks_place_fallback_batches(monkeypatch):
    from world_generation.prompts import create_npc
    from world_generation.step_runtime import StepTranscript

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    primary_place = world.places[0]
    primary_cluster = next(cluster for cluster in diagram.clusters if cluster.place_ref == primary_place.ref)
    for slot in diagram.slots[:6]:
        slot.home_place_ref = primary_place.ref
        slot.current_place_ref = primary_place.ref
        slot.cluster_ref = primary_cluster.ref
    calls = []
    updates = []

    async def fake_generate_place_batch(state, place, planned_slots, *, step_name=None, label=None):
        calls.append((place.ref, len(planned_slots), step_name, label))
        await state.updater(
            step_name,
            "running",
            {"attempts": 1, "label": label},
        )
        planned_refs = {slot.ref for slot in planned_slots}
        batch_npcs = [
            npc
            for npc in world.npcs
            if npc.ref in planned_refs
        ]
        return batch_npcs, StepTranscript(
            name=step_name,
            label=label,
            status="done",
            parsed_payload={"npcs": [npc.model_dump() for npc in batch_npcs]},
        )

    async def updater(step_name, status, payload):
        updates.append((step_name, status, payload))

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
        character_diagram_step=diagram,
        npc_step=None,
    )

    result = asyncio.run(create_npc.run_step(state))

    assert calls[0][:3] == (primary_place.ref, 4, f"npcs_{primary_place.ref.replace('-', '_')}_part_01")
    assert calls[1][:3] == (primary_place.ref, 3, f"npcs_{primary_place.ref.replace('-', '_')}_part_02")
    assert all(call[1] <= create_npc.MAX_NPC_BATCH_SIZE for call in calls)
    assert updates[0] == ("npcs", "running", {"attempts": 0, "error": ""})
    assert updates[1][0] == f"npcs_{primary_place.ref.replace('-', '_')}_part_01"
    assert updates[1][2]["label"] == f"{primary_place.name} NPCs 1/2"
    assert len(result.npc_step.npcs) == NPC_COUNT
    assert result.step_transcripts[-1].name == "npcs"


def test_npc_generation_chunks_character_segments(monkeypatch):
    from world_generation.prompts import create_npc
    from world_generation.step_runtime import StepTranscript

    world = sample_world_draft()
    diagram = sample_character_diagram(world)
    segments = [
        CharacterSegmentDraft(
            ref="segment-family-large",
            cluster_refs=[diagram.slots[0].cluster_ref],
            slot_refs=[slot.ref for slot in diagram.slots[:9]],
            summary="Large test segment.",
        ),
        CharacterSegmentDraft(
            ref="segment-family-rest",
            cluster_refs=sorted({slot.cluster_ref for slot in diagram.slots[9:]}),
            slot_refs=[slot.ref for slot in diagram.slots[9:]],
            summary="Remaining test segment.",
        ),
    ]
    calls = []
    updates = []

    async def fake_generate_segment_batch(state, segment, planned_slots, *, step_name=None, label=None):
        calls.append((segment.ref, len(planned_slots), step_name, label))
        await state.updater(step_name, "running", {"attempts": 1, "label": label})
        planned_refs = {slot.ref for slot in planned_slots}
        batch_npcs = [npc for npc in world.npcs if npc.ref in planned_refs]
        return segment, batch_npcs, StepTranscript(
            name=step_name,
            label=label,
            status="done",
            parsed_payload={"npcs": [npc.model_dump() for npc in batch_npcs]},
        )

    async def updater(step_name, status, payload):
        updates.append((step_name, status, payload))

    monkeypatch.setattr(create_npc, "_generate_segment_batch", fake_generate_segment_batch)
    state = SimpleNamespace(
        prompt="Frontier",
        model=sample_model(),
        updater=updater,
        step_transcripts=[],
        total_latency_ms=0,
        region_step=SimpleNamespace(region=world.region),
        factions_step=SimpleNamespace(factions=world.factions),
        places_step=SimpleNamespace(places=world.places),
        character_diagram_step=diagram,
        relationship_opportunities=[],
        character_segments=segments,
        npc_step=None,
    )

    result = asyncio.run(create_npc.run_step(state))

    assert calls[0][:3] == ("segment-family-large", 4, "npcs_segment_family_large_part_01")
    assert calls[1][:3] == ("segment-family-large", 4, "npcs_segment_family_large_part_02")
    assert calls[2][:3] == ("segment-family-large", 1, "npcs_segment_family_large_part_03")
    assert all(call[1] <= create_npc.MAX_NPC_BATCH_SIZE for call in calls)
    assert updates[1][0] == "npcs_segment_family_large_part_01"
    assert updates[1][2]["label"].endswith("1/3")
    assert len(result.npc_step.npcs) == NPC_COUNT
    assert result.step_transcripts[-1].parsed_payload["npcs"]


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
