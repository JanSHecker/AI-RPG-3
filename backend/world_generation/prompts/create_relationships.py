import asyncio
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field, create_model

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, relationship_shape, render_json_block
from world_generation.schemas import (
    PRIMARY_RELATIONSHIP_TYPES,
    RELATIONSHIP_TARGET_COUNT,
    SECONDARY_RELATIONSHIP_TYPES,
    CharacterSegmentDraft,
    FactionDraft,
    NpcDraft,
    PlaceDraft,
    PlannedRelationshipDraft,
    RegionDraft,
    RelationshipOpportunityDraft,
    RelationshipDraft,
)
from world_generation.step_runtime import AttemptRecord, StepTranscript, run_structured_step, step_label, update_step


MAX_RELATIONSHIP_BATCH_TARGET = 12
RELATIONSHIP_BATCH_NEARBY_PLACE_COUNT = 4


class RelationshipsStep(BaseModel):
    relationships: list[RelationshipDraft] = Field(min_length=1)


@dataclass
class RelationshipBatch:
    ref: str
    label: str
    step_name: str
    npcs: list[NpcDraft]
    places: list[PlaceDraft]
    factions: list[FactionDraft]
    planned_relationships: list[PlannedRelationshipDraft]
    relationship_opportunities: list[RelationshipOpportunityDraft]
    target_count: int


def _relationship_schema(target_count: int) -> type[BaseModel]:
    return create_model(
        f"RelationshipsStep_{target_count}",
        relationships=(list[RelationshipDraft], Field(min_length=target_count, max_length=target_count)),
    )


def _planned_relationship_shape(relationship: PlannedRelationshipDraft) -> dict:
    return {
        "ref": relationship.ref,
        "source_type": "npc",
        "source_ref": relationship.source_ref,
        "target_type": "npc",
        "target_ref": relationship.target_ref,
        "relation_type": relationship.relation_type,
        "description": relationship.description,
    }


def build_messages(
    prompt: str,
    region: RegionDraft,
    places: list[PlaceDraft],
    factions: list[FactionDraft],
    npcs: list[NpcDraft],
    planned_relationships: list[PlannedRelationshipDraft],
    relationship_opportunities: Optional[list[RelationshipOpportunityDraft]],
    target_count: int,
    previous_error: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    required_relationships = [_planned_relationship_shape(relationship) for relationship in planned_relationships]
    prompt_body = f"""World prompt:
{prompt}

Region:
{render_json_block(region.model_dump())}

Places:
{render_json_block([place.model_dump() for place in places])}

Factions:
{render_json_block([faction.model_dump() for faction in factions])}

NPCs:
{render_json_block([npc.model_dump() for npc in npcs])}

Required planned relationships:
{render_json_block(required_relationships)}

Secondary relationship opportunities:
{render_json_block([opportunity.model_dump() for opportunity in (relationship_opportunities or [])])}

Task:
Create final relationships between the provided existing entities for this local graph batch. Return JSON with relationships only.

Target count:
{target_count}

Required JSON shape:
{render_json_block({"relationships": [relationship_shape()]})}

Primary relation_type values:
{render_json_block(PRIMARY_RELATIONSHIP_TYPES)}

Secondary relation_type values:
{render_json_block(SECONDARY_RELATIONSHIP_TYPES)}

Constraints:
- Return exactly the requested number of relationships.
- Include every required planned relationship exactly, preserving ref, source_type, source_ref, target_type, target_ref, and relation_type.
- Required planned relationships are structural primary heritage ties. You may polish descriptions using completed NPC lore, but do not change their source, target, type, or family meaning.
- Each relationship ref must be unique and use the format rel-kebab-case.
- source_type and target_type must be place, faction, or npc.
- source_ref and target_ref must reference provided refs of the matching types.
- For non-required secondary relationships, only use the provided batch refs; do not invent or reference entities outside this batch.
- relation_type must be exactly one of the listed primary or secondary relation_type values.
- Use primary relationship types for intimate or identity-defining ties.
- Use secondary relationship types for social, political, economic, hostile, or situational ties.
- Relationship opportunities are not canon yet. Use them only as inspiration for new secondary relationships.
- Create secondary relationships from the completed NPC lore, place lore, faction lore, and opportunities.
- Do not turn every opportunity into a relationship; choose the most useful narrative links.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the relationship graph specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


def _nearby_places(anchor: PlaceDraft, places: list[PlaceDraft]) -> list[PlaceDraft]:
    ranked = sorted(
        places,
        key=lambda candidate: (
            (candidate.x - anchor.x) ** 2 + (candidate.y - anchor.y) ** 2,
            candidate.ref,
        ),
    )
    return ranked[:RELATIONSHIP_BATCH_NEARBY_PLACE_COUNT]


def _chunk_items(items: list, chunk_size: int) -> list[list]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _safe_step_ref(ref: str) -> str:
    return ref.replace("-", "_").replace(":", "_")


def _relationship_batch_label(prefix: str, index: int, total: int) -> str:
    if total == 1:
        return prefix
    return f"{prefix} {index + 1}/{total}"


def _places_for_npcs(npcs: list[NpcDraft], places: list[PlaceDraft]) -> list[PlaceDraft]:
    places_by_ref = {place.ref: place for place in places}
    relevant_refs: set[str] = set()
    for npc in npcs:
        relevant_refs.update({npc.home_place_ref, npc.current_place_ref})
    relevant = [places_by_ref[ref] for ref in sorted(relevant_refs) if ref in places_by_ref]
    if not relevant:
        return []
    primary = relevant[0]
    seen_refs = {place.ref for place in relevant}
    for place in _nearby_places(primary, places):
        if place.ref not in seen_refs:
            relevant.append(place)
            seen_refs.add(place.ref)
    return relevant


def _factions_for_context(npcs: list[NpcDraft], places: list[PlaceDraft], factions: list[FactionDraft]) -> list[FactionDraft]:
    faction_refs = {npc.faction_ref for npc in npcs if npc.faction_ref}
    faction_refs.update(place.controlling_faction_ref for place in places if place.controlling_faction_ref)
    faction_refs.update(faction.ref for faction in factions if faction.home_place_ref in {place.ref for place in places})
    return [faction for faction in factions if faction.ref in faction_refs]


def _opportunities_for_context(
    npcs: list[NpcDraft],
    places: list[PlaceDraft],
    factions: list[FactionDraft],
    opportunities: list[RelationshipOpportunityDraft],
) -> list[RelationshipOpportunityDraft]:
    npc_refs = {npc.ref for npc in npcs}
    place_refs = {place.ref for place in places}
    faction_refs = {faction.ref for faction in factions}
    return [
        opportunity
        for opportunity in opportunities
        if (not opportunity.slot_refs and not opportunity.place_refs and not opportunity.faction_refs)
        or bool(npc_refs.intersection(opportunity.slot_refs))
        or bool(place_refs.intersection(opportunity.place_refs))
        or bool(faction_refs.intersection(opportunity.faction_refs))
    ]


def _assign_planned_relationships(
    batches: list[tuple[str, str, list[NpcDraft]]],
    planned_relationships: list[PlannedRelationshipDraft],
) -> dict[str, list[PlannedRelationshipDraft]]:
    batch_refs_by_npc: dict[str, list[str]] = {}
    for batch_ref, _, npcs in batches:
        for npc in npcs:
            batch_refs_by_npc.setdefault(npc.ref, []).append(batch_ref)

    assignments = {batch_ref: [] for batch_ref, _, _ in batches}
    fallback_ref = batches[0][0] if batches else ""
    for relationship in planned_relationships:
        source_batches = set(batch_refs_by_npc.get(relationship.source_ref, []))
        target_batches = set(batch_refs_by_npc.get(relationship.target_ref, []))
        shared = sorted(source_batches.intersection(target_batches))
        chosen = shared[0] if shared else sorted(source_batches or target_batches or {fallback_ref})[0]
        assignments[chosen].append(relationship)
    return assignments


def _allocate_batch_targets(
    batch_refs: list[str],
    planned_by_batch: dict[str, list[PlannedRelationshipDraft]],
    target_count: int,
) -> dict[str, int]:
    if not batch_refs:
        return {}
    targets = {batch_ref: len(planned_by_batch.get(batch_ref, [])) for batch_ref in batch_refs}
    remaining = target_count - sum(targets.values())
    index = 0
    while remaining > 0:
        batch_ref = batch_refs[index % len(batch_refs)]
        if targets[batch_ref] < MAX_RELATIONSHIP_BATCH_TARGET or all(targets[ref] >= MAX_RELATIONSHIP_BATCH_TARGET for ref in batch_refs):
            targets[batch_ref] += 1
            remaining -= 1
        index += 1
    return targets


def _base_batches_from_segments(segments: list[CharacterSegmentDraft], npcs: list[NpcDraft]) -> list[tuple[str, str, list[NpcDraft]]]:
    npcs_by_ref = {npc.ref: npc for npc in npcs}
    batches = []
    for segment in segments:
        segment_npcs = [npcs_by_ref[ref] for ref in segment.slot_refs if ref in npcs_by_ref]
        if segment_npcs:
            batches.append((segment.ref, segment.summary or segment.ref, segment_npcs))
    return batches


def _base_batches_by_home_place(npcs: list[NpcDraft], places: list[PlaceDraft]) -> list[tuple[str, str, list[NpcDraft]]]:
    places_by_ref = {place.ref: place for place in places}
    batches = []
    for place_ref in sorted({npc.home_place_ref for npc in npcs}):
        place_npcs = [npc for npc in npcs if npc.home_place_ref == place_ref]
        if place_npcs:
            place = places_by_ref.get(place_ref)
            label = f"{place.name} Relationships" if place else f"{place_ref} Relationships"
            batches.append((place_ref, label, place_npcs))
    return batches


def _split_large_batches(batches: list[tuple[str, str, list[NpcDraft]]]) -> list[tuple[str, str, list[NpcDraft]]]:
    split_batches = []
    for batch_ref, label, npcs in batches:
        chunks = _chunk_items(npcs, MAX_RELATIONSHIP_BATCH_TARGET)
        for index, chunk in enumerate(chunks):
            ref = batch_ref if len(chunks) == 1 else f"{batch_ref}:part-{index + 1:02d}"
            split_batches.append((ref, _relationship_batch_label(label, index, len(chunks)), chunk))
    return split_batches


def _build_relationship_batches(
    *,
    segments: list[CharacterSegmentDraft],
    places: list[PlaceDraft],
    factions: list[FactionDraft],
    npcs: list[NpcDraft],
    planned_relationships: list[PlannedRelationshipDraft],
    relationship_opportunities: list[RelationshipOpportunityDraft],
    target_count: int,
) -> list[RelationshipBatch]:
    base_batches = _base_batches_from_segments(segments, npcs) if segments else []
    if not base_batches:
        base_batches = _base_batches_by_home_place(npcs, places)
    base_batches = _split_large_batches(base_batches)
    planned_by_batch = _assign_planned_relationships(base_batches, planned_relationships)
    batch_refs = [batch_ref for batch_ref, _, _ in base_batches]
    targets = _allocate_batch_targets(batch_refs, planned_by_batch, target_count)
    npcs_by_ref = {npc.ref: npc for npc in npcs}

    batches: list[RelationshipBatch] = []
    for batch_ref, label, batch_npcs in base_batches:
        batch_planned = planned_by_batch.get(batch_ref, [])
        expanded_npcs_by_ref = {npc.ref: npc for npc in batch_npcs}
        for relationship in batch_planned:
            for npc_ref in [relationship.source_ref, relationship.target_ref]:
                if npc_ref in npcs_by_ref:
                    expanded_npcs_by_ref[npc_ref] = npcs_by_ref[npc_ref]
        expanded_npcs = list(expanded_npcs_by_ref.values())
        batch_places = _places_for_npcs(expanded_npcs, places)
        batch_factions = _factions_for_context(expanded_npcs, batch_places, factions)
        batch_opportunities = _opportunities_for_context(expanded_npcs, batch_places, batch_factions, relationship_opportunities)
        batches.append(
            RelationshipBatch(
                ref=batch_ref,
                label=label,
                step_name=f"relationships_{_safe_step_ref(batch_ref)}",
                npcs=expanded_npcs,
                places=batch_places,
                factions=batch_factions,
                planned_relationships=batch_planned,
                relationship_opportunities=batch_opportunities,
                target_count=targets[batch_ref],
            )
        )
    return batches


def _validate_relationships(
    parsed: RelationshipsStep,
    places: list[PlaceDraft],
    factions: list[FactionDraft],
    npcs: list[NpcDraft],
    planned_relationships: list[PlannedRelationshipDraft],
    target_count: Optional[int] = None,
) -> None:
    if target_count is not None and len(parsed.relationships) != target_count:
        raise ValueError(f"Final relationships must contain exactly {target_count} records; got {len(parsed.relationships)}.")
    allowed_refs = {
        "place": {place.ref for place in places},
        "faction": {faction.ref for faction in factions},
        "npc": {npc.ref for npc in npcs},
    }
    seen_refs: set[str] = set()
    for relationship in parsed.relationships:
        if relationship.ref in seen_refs:
            raise ValueError(f"Relationship batch produced duplicate ref {relationship.ref}.")
        seen_refs.add(relationship.ref)
        if relationship.source_type not in allowed_refs:
            raise ValueError(f"Relationship {relationship.ref} has invalid source_type {relationship.source_type}.")
        if relationship.target_type not in allowed_refs:
            raise ValueError(f"Relationship {relationship.ref} has invalid target_type {relationship.target_type}.")
        if relationship.source_ref not in allowed_refs[relationship.source_type]:
            raise ValueError(
                f"Relationship {relationship.ref} source_ref must match the provided {relationship.source_type} refs; got {relationship.source_ref}."
            )
        if relationship.target_ref not in allowed_refs[relationship.target_type]:
            raise ValueError(
                f"Relationship {relationship.ref} target_ref must match the provided {relationship.target_type} refs; got {relationship.target_ref}."
            )

    relationships_by_ref = {relationship.ref: relationship for relationship in parsed.relationships}
    for planned in planned_relationships:
        relationship = relationships_by_ref.get(planned.ref)
        if relationship is None:
            raise ValueError(f"Final relationships must include planned relationship {planned.ref}.")
        expected = _planned_relationship_shape(planned)
        for field in ["source_type", "source_ref", "target_type", "target_ref", "relation_type"]:
            if getattr(relationship, field) != expected[field]:
                raise ValueError(f"Final relationship {planned.ref} changed planned {field}.")


async def _generate_relationship_batch(state, batch: RelationshipBatch) -> tuple[RelationshipBatch, list[RelationshipDraft], StepTranscript]:
    async def batch_updater(step_name: str, status: str, payload: dict) -> None:
        await update_step(getattr(state, "updater", None), step_name, status, **payload, label=batch.label)

    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name=batch.step_name,
        schema=_relationship_schema(batch.target_count),
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            batch.places,
            batch.factions,
            batch.npcs,
            batch.planned_relationships,
            batch.relationship_opportunities,
            batch.target_count,
            previous_error,
            previous_response,
        ),
        updater=batch_updater,
        transcripts=[],
        validate_parsed=lambda parsed: _validate_relationships(
            parsed,
            batch.places,
            batch.factions,
            batch.npcs,
            batch.planned_relationships,
            batch.target_count,
        ),
    )
    transcript.label = batch.label
    return batch, parsed.relationships, transcript


def _combined_transcript(batch_results: list[tuple[RelationshipBatch, list[RelationshipDraft], StepTranscript]]) -> StepTranscript:
    attempts: list[AttemptRecord] = []
    latency_ms = 0
    combined_payload = {"relationships": []}

    for batch, relationships, transcript in batch_results:
        latency_ms += transcript.latency_ms or 0
        combined_payload["relationships"].extend([relationship.model_dump() for relationship in relationships])
        for batch_attempt in transcript.attempts:
            attempts.append(
                AttemptRecord(
                    attempt=len(attempts) + 1,
                    status=batch_attempt.status,
                    error=batch_attempt.error,
                    raw_response=batch_attempt.raw_response,
                    latency_ms=batch_attempt.latency_ms,
                    parsed_payload={
                        "batch_ref": batch.ref,
                        "batch_label": batch.label,
                        "batch_attempt": batch_attempt.attempt,
                        "batch_target_count": batch.target_count,
                        "relationships": [relationship.model_dump() for relationship in relationships],
                    }
                    if batch_attempt.status == "done"
                    else {
                        "batch_ref": batch.ref,
                        "batch_label": batch.label,
                        "batch_attempt": batch_attempt.attempt,
                        "batch_target_count": batch.target_count,
                    },
                )
            )

    return StepTranscript(
        name="relationships",
        label=step_label("relationships"),
        status="done",
        attempts=attempts,
        latency_ms=latency_ms,
        parsed_payload=combined_payload,
    )


@step(name="relationships")
async def run_step(state):
    if (
        state.region_step is None
        or state.places_step is None
        or state.factions_step is None
        or state.npc_step is None
        or state.character_diagram_step is None
    ):
        raise ProviderError("Region, places, factions, NPC, and character diagram steps must complete before relationship generation.")
    planned_relationships = state.character_diagram_step.relationships
    target_count = max(len(planned_relationships), RELATIONSHIP_TARGET_COUNT)
    batches = _build_relationship_batches(
        segments=list(getattr(state, "character_segments", [])),
        places=state.places_step.places,
        factions=state.factions_step.factions,
        npcs=state.npc_step.npcs,
        planned_relationships=planned_relationships,
        relationship_opportunities=list(getattr(state, "relationship_opportunities", [])),
        target_count=target_count,
    )
    if not batches:
        raise ProviderError("Relationship generation could not build any batches.")

    await update_step(state.updater, "relationships", "running", attempts=0, error="")
    try:
        batch_results = await asyncio.gather(*[_generate_relationship_batch(state, batch) for batch in batches])
    except Exception as exc:
        message = str(exc)
        await update_step(state.updater, "relationships", "failed", attempts=0, error=message, raw_response="")
        raise

    relationships = [relationship for _, batch_relationships, _ in batch_results for relationship in batch_relationships]
    parsed = RelationshipsStep(relationships=relationships)
    _validate_relationships(
        parsed,
        state.places_step.places,
        state.factions_step.factions,
        state.npc_step.npcs,
        planned_relationships,
        target_count,
    )
    transcript = _combined_transcript(batch_results)
    state.step_transcripts.append(transcript)
    state.relationships_step = parsed
    state.total_latency_ms += transcript.latency_ms or 0
    await update_step(
        state.updater,
        "relationships",
        "done",
        attempts=len(transcript.attempts),
        error="",
        raw_response="",
        parsed_payload=transcript.parsed_payload,
        latency_ms=transcript.latency_ms,
    )
    return state
