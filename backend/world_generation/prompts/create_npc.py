import asyncio
from typing import Optional

from pydantic import BaseModel, Field, create_model

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, npc_shape, render_json_block
from world_generation.schemas import (
    NPC_COUNT,
    PERSONALITIES,
    CharacterSegmentDraft,
    CharacterSlotDraft,
    FactionDraft,
    NpcDraft,
    PlaceDraft,
    PlannedRelationshipDraft,
    RegionDraft,
    RelationshipOpportunityDraft,
)
from world_generation.step_runtime import AttemptRecord, StepTranscript, run_structured_step, step_label, update_step


NEARBY_PLACE_COUNT = 3
MAX_NPC_BATCH_SIZE = 4


class NPCStep(BaseModel):
    npcs: list[NpcDraft] = Field(min_length=NPC_COUNT, max_length=NPC_COUNT)


AGE_BAND_RANGES = {
    "child": (12, 14),
    "teen": (15, 19),
    "young adult": (20, 29),
    "adult": (30, 59),
    "elder": (60, 95),
}


def _batch_schema(batch_size: int) -> type[BaseModel]:
    return create_model(
        f"NPCBatchStep_{batch_size}",
        npcs=(list[NpcDraft], Field(min_length=batch_size, max_length=batch_size)),
    )


def _slot_prompt_payload(slot: CharacterSlotDraft) -> dict:
    low, high = AGE_BAND_RANGES[slot.age_band]
    payload = slot.model_dump()
    payload.pop("age_band", None)
    payload["age_range"] = {"min": low, "max": high}
    return payload


def _nearby_places(primary_place: PlaceDraft, places: list[PlaceDraft]) -> list[PlaceDraft]:
    ranked = sorted(
        places,
        key=lambda candidate: (
            (candidate.x - primary_place.x) ** 2 + (candidate.y - primary_place.y) ** 2,
            candidate.ref,
        ),
    )
    return ranked[:NEARBY_PLACE_COUNT]


def _batch_label(place: PlaceDraft, batch_size: int) -> str:
    npc_label = "NPC" if batch_size == 1 else "NPCs"
    return f"{place.name} {npc_label}"


def _chunk_slots(slots: list[CharacterSlotDraft], chunk_size: int = MAX_NPC_BATCH_SIZE) -> list[list[CharacterSlotDraft]]:
    return [slots[index : index + chunk_size] for index in range(0, len(slots), chunk_size)]


def _chunk_step_name(prefix_ref: str, part_index: int, part_count: int) -> str:
    base = prefix_ref.replace("-", "_")
    if part_count == 1:
        return f"npcs_{base}"
    return f"npcs_{base}_part_{part_index + 1:02d}"


def _chunk_label(base_label: str, part_index: int, part_count: int) -> str:
    if part_count == 1:
        return base_label
    return f"{base_label} {part_index + 1}/{part_count}"


def _segment_label(segment: CharacterSegmentDraft, planned_slots: list[CharacterSlotDraft], places: list[PlaceDraft]) -> str:
    places_by_ref = {place.ref: place for place in places}
    home_counts: dict[str, int] = {}
    for slot in planned_slots:
        home_counts[slot.home_place_ref] = home_counts.get(slot.home_place_ref, 0) + 1
    dominant_place_ref = max(home_counts, key=lambda ref: (home_counts[ref], ref)) if home_counts else None
    dominant_place = places_by_ref.get(dominant_place_ref) if dominant_place_ref else None
    place_name = dominant_place.name if dominant_place else segment.ref
    return f"{place_name} Family Segment"


def build_messages(
    prompt: str,
    region: RegionDraft,
    primary_place: PlaceDraft,
    nearby_places: list[PlaceDraft],
    factions: list[FactionDraft],
    planned_slots: list[CharacterSlotDraft],
    planned_relationships: list[PlannedRelationshipDraft],
    relationship_opportunities: Optional[list[RelationshipOpportunityDraft]] = None,
    segment: Optional[CharacterSegmentDraft] = None,
    previous_error: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    allowed_faction_refs = [faction.ref for faction in factions]
    allowed_personalities = PERSONALITIES
    planned_refs = [slot.ref for slot in planned_slots]
    npc_example = npc_shape()
    npc_example["faction_ref"] = None
    npc_example["home_place_ref"] = primary_place.ref
    npc_example["current_place_ref"] = nearby_places[0].ref if nearby_places else primary_place.ref
    prompt_body = f"""

Region:
{render_json_block(region.model_dump())}

Primary place:
{render_json_block(primary_place.model_dump())}

Nearby places:
{render_json_block([place.model_dump() for place in nearby_places])}

Factions:
{render_json_block([faction.model_dump() for faction in factions])}

Planned character slots for this place:
{render_json_block([_slot_prompt_payload(slot) for slot in planned_slots])}

Planned relationships involving these slots:
{render_json_block([relationship.model_dump() for relationship in planned_relationships])}

Relationship opportunities for later secondary meaning:
{render_json_block([opportunity.model_dump() for opportunity in (relationship_opportunities or [])])}

Generation segment:
{render_json_block(segment.model_dump() if segment else None)}

Task:
Create NPCs for this family/heritage graph segment from the planned character slots. Return JSON with npcs only.

Target count:
{len(planned_slots)}

Required JSON shape:
{render_json_block({"npcs": [npc_example]})}

Allowed faction_ref values:
{render_json_block(allowed_faction_refs)}

Allowed personality values:
{render_json_block(allowed_personalities)}

Constraints:
- Return exactly the requested number of npcs.
- Each npc ref must exactly match one planned slot ref. Planned refs are {render_json_block(planned_refs)}.
- home_place_ref, current_place_ref, and faction_ref must exactly match the planned slot values.
- age must be within the planned slot age_range, inclusive.
- personality must be exactly 3 unique values from the allowed personality values list.
- Do not invent personality synonyms. For example, use "stable" instead of "steady" and "empathetic" instead of "sensitive".
- Use role_hint, cluster_ref, and planned relationships as strong guidance for job, personality, and lore.
- Keep the cast grounded in the local life of the primary place while honoring cross-place family context.
- Relationship opportunities are context only; they may inspire lore, but do not output relationship records.
- Write useful prose lore in Markdown.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the NPC specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


def _age_matches_band(age: int, age_band: str) -> bool:
    low, high = AGE_BAND_RANGES[age_band]
    return low <= age <= high


def _normalize_npc_batch_ages(parsed: BaseModel, planned_slots: list[CharacterSlotDraft]) -> None:
    planned_by_ref = {slot.ref: slot for slot in planned_slots}
    for npc in parsed.npcs:
        planned = planned_by_ref.get(npc.ref)
        if not planned:
            continue
        low, high = AGE_BAND_RANGES[planned.age_band]
        npc.age = max(low, min(high, npc.age))


def _prepare_and_validate_npc_batch(parsed: BaseModel, planned_slots: list[CharacterSlotDraft], factions: list[FactionDraft]) -> None:
    _normalize_npc_batch_ages(parsed, planned_slots)
    _validate_npc_batch(parsed, planned_slots, factions)


def _validate_npc_batch(parsed: BaseModel, planned_slots: list[CharacterSlotDraft], factions: list[FactionDraft]) -> None:
    planned_by_ref = {slot.ref: slot for slot in planned_slots}
    expected_refs = set(planned_by_ref)
    allowed_faction_refs = {faction.ref for faction in factions}
    allowed_personalities = set(PERSONALITIES)
    seen_refs = {npc.ref for npc in parsed.npcs}
    if seen_refs != expected_refs:
        raise ValueError(f"NPC batch refs must exactly match planned refs. Missing: {sorted(expected_refs - seen_refs)}. Extra: {sorted(seen_refs - expected_refs)}.")
    for npc in parsed.npcs:
        planned = planned_by_ref[npc.ref]
        if npc.home_place_ref != planned.home_place_ref:
            raise ValueError(f"NPC {npc.ref} changed home_place_ref from {planned.home_place_ref} to {npc.home_place_ref}.")
        if npc.current_place_ref != planned.current_place_ref:
            raise ValueError(f"NPC {npc.ref} changed current_place_ref from {planned.current_place_ref} to {npc.current_place_ref}.")
        if npc.faction_ref != planned.faction_ref:
            raise ValueError(f"NPC {npc.ref} changed faction_ref from {planned.faction_ref} to {npc.faction_ref}.")
        if npc.faction_ref and npc.faction_ref not in allowed_faction_refs:
            raise ValueError(
                f"NPC {npc.ref} faction_ref must be null or one of {sorted(allowed_faction_refs)}; got {npc.faction_ref}."
            )
        if not _age_matches_band(npc.age, planned.age_band):
            low, high = AGE_BAND_RANGES[planned.age_band]
            raise ValueError(f"NPC {npc.ref} age {npc.age} must be within planned age_range {low}-{high}.")
        invalid_personalities = [entry for entry in npc.personality if entry not in allowed_personalities]
        if invalid_personalities:
            raise ValueError(
                f"NPC {npc.ref} personality values must be from the personality catalog; got {invalid_personalities}."
            )


def _relationships_for_slots(slots: list[CharacterSlotDraft], relationships: list[PlannedRelationshipDraft]) -> list[PlannedRelationshipDraft]:
    refs = {slot.ref for slot in slots}
    return [
        relationship
        for relationship in relationships
        if relationship.source_ref in refs or relationship.target_ref in refs
    ]


def _opportunities_for_slots(slots: list[CharacterSlotDraft], opportunities: list[RelationshipOpportunityDraft]) -> list[RelationshipOpportunityDraft]:
    refs = {slot.ref for slot in slots}
    return [
        opportunity
        for opportunity in opportunities
        if not opportunity.slot_refs or refs.intersection(opportunity.slot_refs)
    ]


def _places_for_slots(slots: list[CharacterSlotDraft], places: list[PlaceDraft]) -> tuple[PlaceDraft, list[PlaceDraft]]:
    places_by_ref = {place.ref: place for place in places}
    home_counts: dict[str, int] = {}
    for slot in slots:
        home_counts[slot.home_place_ref] = home_counts.get(slot.home_place_ref, 0) + 1
    primary_ref = max(home_counts, key=lambda ref: (home_counts[ref], ref))
    primary = places_by_ref[primary_ref]
    relevant_refs = {primary_ref}
    for slot in slots:
        relevant_refs.update({slot.home_place_ref, slot.current_place_ref})
    relevant = [places_by_ref[ref] for ref in sorted(relevant_refs) if ref in places_by_ref]
    for nearby in _nearby_places(primary, places):
        if nearby.ref not in relevant_refs:
            relevant.append(nearby)
    return primary, relevant[: max(NEARBY_PLACE_COUNT, len(relevant))]


async def _generate_place_batch(
    state,
    place: PlaceDraft,
    planned_slots: list[CharacterSlotDraft],
    *,
    step_name: Optional[str] = None,
    label: Optional[str] = None,
) -> tuple[list[NpcDraft], StepTranscript]:
    nearby_places = _nearby_places(place, state.places_step.places)
    planned_relationships = _relationships_for_slots(planned_slots, state.character_diagram_step.relationships)
    label = label or _batch_label(place, len(planned_slots))

    async def batch_updater(step_name: str, status: str, payload: dict) -> None:
        await update_step(getattr(state, "updater", None), step_name, status, **payload, label=label)

    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name=step_name or f"npcs_{place.ref.replace('-', '_')}",
        schema=_batch_schema(len(planned_slots)),
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            place,
            nearby_places,
            state.factions_step.factions,
            planned_slots,
            planned_relationships,
            [],
            None,
            previous_error,
            previous_response,
        ),
        updater=batch_updater,
        transcripts=[],
        validate_parsed=lambda parsed: _prepare_and_validate_npc_batch(
            parsed,
            planned_slots,
            state.factions_step.factions,
        ),
    )
    transcript.label = label
    return parsed.npcs, transcript


async def _generate_segment_batch(
    state,
    segment: CharacterSegmentDraft,
    planned_slots: list[CharacterSlotDraft],
    *,
    step_name: Optional[str] = None,
    label: Optional[str] = None,
) -> tuple[CharacterSegmentDraft, list[NpcDraft], StepTranscript]:
    primary_place, relevant_places = _places_for_slots(planned_slots, state.places_step.places)
    planned_relationships = _relationships_for_slots(planned_slots, state.character_diagram_step.relationships)
    relationship_opportunities = _opportunities_for_slots(planned_slots, getattr(state, "relationship_opportunities", []))
    label = label or _segment_label(segment, planned_slots, state.places_step.places)

    async def batch_updater(step_name: str, status: str, payload: dict) -> None:
        await update_step(getattr(state, "updater", None), step_name, status, **payload, label=label)

    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name=step_name or f"npcs_{segment.ref.replace('-', '_')}",
        schema=_batch_schema(len(planned_slots)),
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            primary_place,
            relevant_places,
            state.factions_step.factions,
            planned_slots,
            planned_relationships,
            relationship_opportunities,
            segment,
            previous_error,
            previous_response,
        ),
        updater=batch_updater,
        transcripts=[],
        validate_parsed=lambda parsed: _prepare_and_validate_npc_batch(
            parsed,
            planned_slots,
            state.factions_step.factions,
        ),
    )
    transcript.label = label
    return segment, parsed.npcs, transcript


def _combined_transcript(batch_results: list[tuple[str, str, StepTranscript, list[NpcDraft]]]) -> StepTranscript:
    attempts: list[AttemptRecord] = []
    latency_ms = 0
    combined_payload = {"npcs": []}

    for batch_ref, batch_label, transcript, npcs in batch_results:
        latency_ms += transcript.latency_ms or 0
        combined_payload["npcs"].extend([npc.model_dump() for npc in npcs])
        for batch_attempt in transcript.attempts:
            attempts.append(
                AttemptRecord(
                    attempt=len(attempts) + 1,
                    status=batch_attempt.status,
                    error=batch_attempt.error,
                    raw_response=batch_attempt.raw_response,
                    latency_ms=batch_attempt.latency_ms,
                    parsed_payload={
                        "batch_ref": batch_ref,
                        "batch_label": batch_label,
                        "batch_attempt": batch_attempt.attempt,
                        "batch_size": len(npcs),
                        "npcs": [npc.model_dump() for npc in npcs],
                    }
                    if batch_attempt.status == "done"
                    else {"batch_ref": batch_ref, "batch_label": batch_label, "batch_attempt": batch_attempt.attempt},
                )
            )

    return StepTranscript(
        name="npcs",
        label=step_label("npcs"),
        status="done",
        attempts=attempts,
        latency_ms=latency_ms,
        parsed_payload=combined_payload,
    )


@step(name="npcs")
async def run_step(state):
    if state.region_step is None or state.places_step is None or state.factions_step is None or state.character_diagram_step is None:
        raise ProviderError("Region, places, factions, and character diagram steps must complete before NPC generation.")

    slots_by_ref = {slot.ref: slot for slot in state.character_diagram_step.slots}
    segments: list[CharacterSegmentDraft] = list(getattr(state, "character_segments", []))
    if not segments:
        slots_by_home_place = {
            place.ref: [slot for slot in state.character_diagram_step.slots if slot.home_place_ref == place.ref]
            for place in state.places_step.places
        }
        places_with_slots = [place for place in state.places_step.places if slots_by_home_place[place.ref]]
        place_jobs = []
        for place in places_with_slots:
            chunks = _chunk_slots(slots_by_home_place[place.ref])
            base_label = _batch_label(place, len(slots_by_home_place[place.ref]))
            for part_index, chunk in enumerate(chunks):
                step_name = _chunk_step_name(place.ref, part_index, len(chunks))
                place_jobs.append(
                    (
                        place.ref if len(chunks) == 1 else f"{place.ref}:part-{part_index + 1:02d}",
                        place,
                        chunk,
                        step_name,
                        _chunk_label(base_label, part_index, len(chunks)),
                    )
                )
        await update_step(state.updater, "npcs", "running", attempts=0, error="")
        try:
            place_batch_results = await asyncio.gather(
                *[
                    _generate_place_batch(state, place, chunk, step_name=step_name, label=label)
                    for _, place, chunk, step_name, label in place_jobs
                ]
            )
        except Exception as exc:
            message = str(exc)
            await update_step(state.updater, "npcs", "failed", attempts=0, error=message, raw_response="")
            raise

        combined_results = [
            (batch_ref, transcript.label, transcript, npcs)
            for (batch_ref, _, _, _, _), (npcs, transcript) in zip(place_jobs, place_batch_results)
        ]
        all_npcs = [npc for npcs, _ in place_batch_results for npc in npcs]

        if len(all_npcs) != NPC_COUNT:
            raise ProviderError(f"NPC generation produced {len(all_npcs)} NPCs instead of {NPC_COUNT}.")

        if len({npc.ref for npc in all_npcs}) != len(all_npcs):
            raise ProviderError("NPC generation produced duplicate refs across location batches.")

        transcript = _combined_transcript(combined_results)
        state.step_transcripts.append(transcript)
        state.npc_step = NPCStep(npcs=all_npcs)
        state.total_latency_ms += transcript.latency_ms or 0
        await update_step(
            state.updater,
            "npcs",
            "done",
            attempts=len(transcript.attempts),
            error="",
            raw_response="",
            parsed_payload=transcript.parsed_payload,
            latency_ms=transcript.latency_ms,
        )
        return state

    await update_step(state.updater, "npcs", "running", attempts=0, error="")
    segment_jobs = []
    for segment in segments:
        segment_slots = [slots_by_ref[slot_ref] for slot_ref in segment.slot_refs if slot_ref in slots_by_ref]
        chunks = _chunk_slots(segment_slots)
        base_label = _segment_label(segment, segment_slots, state.places_step.places)
        for part_index, chunk in enumerate(chunks):
            step_name = _chunk_step_name(segment.ref, part_index, len(chunks))
            segment_jobs.append(
                (
                    segment.ref if len(chunks) == 1 else f"{segment.ref}:part-{part_index + 1:02d}",
                    segment,
                    chunk,
                    step_name,
                    _chunk_label(base_label, part_index, len(chunks)),
                )
            )
    try:
        batch_results = await asyncio.gather(
            *[
                _generate_segment_batch(
                    state,
                    segment,
                    chunk,
                    step_name=step_name,
                    label=label,
                )
                for _, segment, chunk, step_name, label in segment_jobs
            ]
        )
    except Exception as exc:
        message = str(exc)
        await update_step(state.updater, "npcs", "failed", attempts=0, error=message, raw_response="")
        raise

    combined_results = [
        (batch_ref, transcript.label, transcript, npcs)
        for (batch_ref, _, _, _, _), (_, npcs, transcript) in zip(segment_jobs, batch_results)
    ]
    all_npcs = [npc for _, npcs, _ in batch_results for npc in npcs]

    if len(all_npcs) != NPC_COUNT:
        raise ProviderError(f"NPC generation produced {len(all_npcs)} NPCs instead of {NPC_COUNT}.")

    if len({npc.ref for npc in all_npcs}) != len(all_npcs):
        raise ProviderError("NPC generation produced duplicate refs across location batches.")

    transcript = _combined_transcript(combined_results)
    state.step_transcripts.append(transcript)
    state.npc_step = NPCStep(npcs=all_npcs)
    state.total_latency_ms += transcript.latency_ms or 0
    await update_step(
        state.updater,
        "npcs",
        "done",
        attempts=len(transcript.attempts),
        error="",
        raw_response="",
        parsed_payload=transcript.parsed_payload,
        latency_ms=transcript.latency_ms,
    )
    return state
