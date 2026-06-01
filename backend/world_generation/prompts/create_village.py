import asyncio
from typing import Optional

from pydantic import BaseModel, Field, create_model

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, place_shape, render_json_block
from world_generation.schemas import PLACE_COUNT, PLACE_TYPES, TERRAINS, FactionDraft, LocationPlanBatch, LocationPlanStep, PlaceDraft, RegionDraft
from world_generation.step_runtime import AttemptRecord, StepTranscript, run_structured_step, step_label, update_step


class PlacesStep(BaseModel):
    places: list[PlaceDraft] = Field(min_length=PLACE_COUNT, max_length=PLACE_COUNT)


def _batch_schema(batch: LocationPlanBatch) -> type[BaseModel]:
    return create_model(
        f"PlacesBatchStep_{batch.batch_id.replace('-', '_')}",
        places=(list[PlaceDraft], Field(min_length=len(batch.slots), max_length=len(batch.slots))),
    )


def _batch_label(batch: LocationPlanBatch, factions: list[FactionDraft]) -> str:
    factions_by_ref = {faction.ref: faction for faction in factions}
    if batch.faction_ref and batch.faction_ref in factions_by_ref:
        return f"{factions_by_ref[batch.faction_ref].name} Locations"
    if batch.batch_kind == "neutral_villages":
        return "Neutral Villages"
    if batch.batch_kind == "dangerous_sites":
        return "Dangerous Sites"
    return f"Places batch {batch.batch_id.removeprefix('batch-').replace('-', ' ')}"


def build_messages(
    prompt: str,
    region: RegionDraft,
    factions: list[FactionDraft],
    batch: LocationPlanBatch,
    previous_error: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    expected_refs = [slot.ref for slot in batch.slots]
    prompt_body = f"""World prompt:
{prompt}

Region:
{render_json_block(region.model_dump())}

Factions and required place planning notes:
{render_json_block([faction.model_dump() for faction in factions])}

Location plan batch to flesh out:
{render_json_block(batch.model_dump())}

Task:
Create finished places for this location-plan batch. Return JSON with places only.

Target count:
{len(batch.slots)}

Required JSON shape:
{render_json_block({"places": [place_shape()]})}

Schema notes:
{render_json_block({
    "allowed_place_types": PLACE_TYPES,
    "suggested_terrains": TERRAINS,
    "danger_level": "1-5",
})}

Constraints:
- Return exactly the requested number of places.
- Preserve every planned ref exactly; expected refs are {render_json_block(expected_refs)}.
- Preserve each planned place_type exactly.
- Preserve controlling_faction_ref from the plan: use the slot faction_ref, or null when faction_ref is null.
- Keep x and y within 8 map units of the planned slot coordinates.
- Use the slot terrain_hint, danger_level_hint, population_hint, purpose, and theme as strong guidance.
- Use faction required_places as creative guidance for faction-controlled batches.
- Write useful prose lore in Markdown.
- Do not invent faction refs; use null for controlling_faction_ref if unsure.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the settlements and locations specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


async def _generate_batch(state, batch: LocationPlanBatch) -> tuple[LocationPlanBatch, list[PlaceDraft], StepTranscript]:
    label = _batch_label(batch, state.factions_step.factions)

    async def batch_updater(step_name: str, status: str, payload: dict) -> None:
        await update_step(state.updater, step_name, status, **payload, label=label)

    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name=f"places_{batch.batch_id.replace('-', '_')}",
        schema=_batch_schema(batch),
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            state.factions_step.factions,
            batch,
            previous_error,
            previous_response,
        ),
        updater=batch_updater,
        transcripts=[],
    )
    transcript.label = label
    return batch, parsed.places, transcript


def _validate_places_against_plan(places: list[PlaceDraft], plan: LocationPlanStep, factions: list[FactionDraft]) -> None:
    planned_by_ref = {slot.ref: slot for slot in plan.slots}
    place_refs = [place.ref for place in places]
    if len(place_refs) != PLACE_COUNT:
        raise ProviderError(f"Place generation produced {len(place_refs)} places instead of {PLACE_COUNT}.")
    if len(set(place_refs)) != len(place_refs):
        raise ProviderError("Place generation produced duplicate refs across location batches.")
    missing = sorted(set(planned_by_ref) - set(place_refs))
    extra = sorted(set(place_refs) - set(planned_by_ref))
    if missing or extra:
        raise ProviderError(f"Place generation did not match the location plan. Missing: {missing}. Extra: {extra}.")

    faction_refs = {faction.ref for faction in factions}
    for place in places:
        slot = planned_by_ref[place.ref]
        if place.place_type != slot.place_type:
            raise ProviderError(f"Place {place.ref} changed type from {slot.place_type} to {place.place_type}.")
        if place.controlling_faction_ref != slot.faction_ref:
            raise ProviderError(f"Place {place.ref} changed controlling faction from {slot.faction_ref} to {place.controlling_faction_ref}.")
        if place.controlling_faction_ref and place.controlling_faction_ref not in faction_refs:
            raise ProviderError(f"Place {place.ref} references unknown faction.")
        if abs(place.x - slot.x) > 8 or abs(place.y - slot.y) > 8:
            raise ProviderError(f"Place {place.ref} moved too far from its planned coordinates.")


def _combined_transcript(batch_results: list[tuple[LocationPlanBatch, list[PlaceDraft], StepTranscript]]) -> StepTranscript:
    attempts: list[AttemptRecord] = []
    latency_ms = 0
    combined_payload = {"places": []}
    for batch, places, transcript in batch_results:
        latency_ms += transcript.latency_ms or 0
        combined_payload["places"].extend([place.model_dump() for place in places])
        for batch_attempt in transcript.attempts:
            attempts.append(
                AttemptRecord(
                    attempt=len(attempts) + 1,
                    status=batch_attempt.status,
                    error=batch_attempt.error,
                    raw_response=batch_attempt.raw_response,
                    latency_ms=batch_attempt.latency_ms,
                    parsed_payload={
                        "batch_id": batch.batch_id,
                        "batch_attempt": batch_attempt.attempt,
                        "places": [place.model_dump() for place in places],
                    }
                    if batch_attempt.status == "done"
                    else {"batch_id": batch.batch_id, "batch_attempt": batch_attempt.attempt},
                )
            )
    return StepTranscript(
        name="villages_places",
        label=step_label("villages_places"),
        status="done",
        attempts=attempts,
        latency_ms=latency_ms,
        parsed_payload=combined_payload,
    )


@step(name="villages_places")
async def run_step(state):
    if state.region_step is None or state.factions_step is None or state.location_plan_step is None:
        raise ProviderError("Region, factions, and location plan steps must complete before places generation.")
    await update_step(state.updater, "villages_places", "running", attempts=0, error="")
    try:
        batch_results = await asyncio.gather(
            *[_generate_batch(state, batch) for batch in state.location_plan_step.batches]
        )
        places = [place for _, batch_places, _ in batch_results for place in batch_places]
        _validate_places_against_plan(places, state.location_plan_step, state.factions_step.factions)
    except Exception as exc:
        await update_step(state.updater, "villages_places", "failed", attempts=0, error=str(exc), raw_response="")
        raise

    transcript = _combined_transcript(batch_results)
    state.step_transcripts.append(transcript)
    state.places_step = PlacesStep(places=places)
    state.total_latency_ms += transcript.latency_ms or 0
    await update_step(
        state.updater,
        "villages_places",
        "done",
        attempts=len(transcript.attempts),
        error="",
        raw_response="",
        parsed_payload=transcript.parsed_payload,
        latency_ms=transcript.latency_ms,
    )
    return state
