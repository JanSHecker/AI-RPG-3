import asyncio
from math import floor
from typing import Optional

from pydantic import BaseModel, Field, create_model

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, npc_shape, render_json_block
from world_generation.schemas import NPC_COUNT, FactionDraft, NpcDraft, PlaceDraft, RegionDraft
from world_generation.step_runtime import AttemptRecord, StepTranscript, run_structured_step, step_label, update_step


NEARBY_PLACE_COUNT = 3


class NPCStep(BaseModel):
    npcs: list[NpcDraft] = Field(min_length=NPC_COUNT, max_length=NPC_COUNT)


def _batch_schema(batch_size: int) -> type[BaseModel]:
    return create_model(
        f"NPCBatchStep_{batch_size}",
        npcs=(list[NpcDraft], Field(min_length=batch_size, max_length=batch_size)),
    )


def _distribute_npc_counts(places: list[PlaceDraft]) -> dict[str, int]:
    if not places:
        raise ProviderError("At least one place is required before NPC generation.")

    counts = {place.ref: 1 for place in places}
    remaining = NPC_COUNT - len(places)
    if remaining < 0:
        raise ProviderError("NPC target count is smaller than the number of places.")
    if remaining == 0:
        return counts

    weights: dict[str, int] = {}
    for place in places:
        weight = max(place.population_estimate, 1)
        if place.place_type in {"dungeon", "forest", "ruin"}:
            weight = max(1, weight // 4)
        if place.controlling_faction_ref:
            weight = int(weight * 1.25) + 10
        weights[place.ref] = max(weight, 1)
    total_weight = sum(weights.values())
    fractional_parts: list[tuple[float, str]] = []

    for place in places:
        exact_share = remaining * weights[place.ref] / total_weight
        extra = floor(exact_share)
        counts[place.ref] += extra
        fractional_parts.append((exact_share - extra, place.ref))

    assigned = sum(counts.values())
    for _, place_ref in sorted(fractional_parts, reverse=True)[: NPC_COUNT - assigned]:
        counts[place_ref] += 1
    return counts


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


def build_messages(
    prompt: str,
    region: RegionDraft,
    primary_place: PlaceDraft,
    nearby_places: list[PlaceDraft],
    factions: list[FactionDraft],
    batch_size: int,
    previous_error: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    nearby_place_refs = [place.ref for place in nearby_places]
    allowed_faction_refs = [faction.ref for faction in factions]
    npc_example = npc_shape()
    npc_example["faction_ref"] = None
    npc_example["home_place_ref"] = primary_place.ref
    npc_example["current_place_ref"] = nearby_place_refs[0] if nearby_place_refs else primary_place.ref
    prompt_body = f"""World prompt:
{prompt}

Region:
{render_json_block(region.model_dump())}

Primary place:
{render_json_block(primary_place.model_dump())}

Nearby places:
{render_json_block([place.model_dump() for place in nearby_places])}

Factions:
{render_json_block([faction.model_dump() for faction in factions])}

Task:
Create NPCs for this single location batch. Return JSON with npcs only.

Target count:
{batch_size}

Required JSON shape:
{render_json_block({"npcs": [npc_example]})}

Allowed faction_ref values:
{render_json_block(allowed_faction_refs)}

Constraints:
- Return exactly the requested number of npcs.
- Each npc ref must be unique and use the format npc-{primary_place.ref.removeprefix("place-")}-kebab-case.
- home_place_ref must always be {primary_place.ref}.
- current_place_ref must be one of {render_json_block(nearby_place_refs)}.
- faction_ref must be null or exactly one of the allowed faction_ref values; never invent a faction ref from a faction name.
- age must be 12-95.
- Keep the cast grounded in the local life of the primary place.
- Write useful prose lore in Markdown.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the NPC specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


def _validate_npc_batch(parsed: BaseModel, primary_place: PlaceDraft, nearby_places: list[PlaceDraft], factions: list[FactionDraft]) -> None:
    allowed_place_refs = {place.ref for place in nearby_places}
    allowed_faction_refs = {faction.ref for faction in factions}
    seen_refs: set[str] = set()
    for npc in parsed.npcs:
        if npc.ref in seen_refs:
            raise ValueError(f"NPC batch produced duplicate ref {npc.ref}.")
        seen_refs.add(npc.ref)
        if npc.home_place_ref != primary_place.ref:
            raise ValueError(f"NPC {npc.ref} changed home_place_ref from {primary_place.ref} to {npc.home_place_ref}.")
        if npc.current_place_ref not in allowed_place_refs:
            raise ValueError(
                f"NPC {npc.ref} current_place_ref must be one of {sorted(allowed_place_refs)}; got {npc.current_place_ref}."
            )
        if npc.faction_ref and npc.faction_ref not in allowed_faction_refs:
            raise ValueError(
                f"NPC {npc.ref} faction_ref must be null or one of {sorted(allowed_faction_refs)}; got {npc.faction_ref}."
            )


async def _generate_place_batch(state, place: PlaceDraft, batch_size: int) -> tuple[list[NpcDraft], StepTranscript]:
    nearby_places = _nearby_places(place, state.places_step.places)
    label = _batch_label(place, batch_size)

    async def batch_updater(step_name: str, status: str, payload: dict) -> None:
        await update_step(getattr(state, "updater", None), step_name, status, **payload, label=label)

    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name=f"npcs_{place.ref.replace('-', '_')}",
        schema=_batch_schema(batch_size),
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            place,
            nearby_places,
            state.factions_step.factions,
            batch_size,
            previous_error,
            previous_response,
        ),
        updater=batch_updater,
        transcripts=[],
        validate_parsed=lambda parsed: _validate_npc_batch(
            parsed,
            place,
            nearby_places,
            state.factions_step.factions,
        ),
    )
    transcript.label = label
    return parsed.npcs, transcript


def _combined_transcript(place_results: list[tuple[PlaceDraft, StepTranscript, list[NpcDraft]]]) -> StepTranscript:
    attempts: list[AttemptRecord] = []
    latency_ms = 0
    combined_payload = {"npcs": []}

    for place, transcript, npcs in place_results:
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
                        "place_ref": place.ref,
                        "batch_attempt": batch_attempt.attempt,
                        "batch_size": len(npcs),
                        "npcs": [npc.model_dump() for npc in npcs],
                    }
                    if batch_attempt.status == "done"
                    else {"place_ref": place.ref, "batch_attempt": batch_attempt.attempt},
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
    if state.region_step is None or state.places_step is None or state.factions_step is None:
        raise ProviderError("Region, places, and factions steps must complete before NPC generation.")

    counts_by_place = _distribute_npc_counts(state.places_step.places)
    await update_step(state.updater, "npcs", "running", attempts=0, error="")
    try:
        batch_results = await asyncio.gather(
            *[
                _generate_place_batch(state, place, counts_by_place[place.ref])
                for place in state.places_step.places
            ]
        )
    except Exception as exc:
        message = str(exc)
        await update_step(state.updater, "npcs", "failed", attempts=0, error=message, raw_response="")
        raise

    place_results = [
        (place, transcript, npcs)
        for place, (npcs, transcript) in zip(state.places_step.places, batch_results)
    ]
    all_npcs = [npc for _, _, npcs in place_results for npc in npcs]

    if len(all_npcs) != NPC_COUNT:
        raise ProviderError(f"NPC generation produced {len(all_npcs)} NPCs instead of {NPC_COUNT}.")

    if len({npc.ref for npc in all_npcs}) != len(all_npcs):
        raise ProviderError("NPC generation produced duplicate refs across location batches.")

    transcript = _combined_transcript(place_results)
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
