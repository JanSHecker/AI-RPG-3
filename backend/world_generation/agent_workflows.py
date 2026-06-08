from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Optional

from model_catalog import ConfiguredModel
from providers import ProviderError, chat_completion, strict_json_schema
from world_generation.agent_framework_compat import AGENT_FRAMEWORK_AVAILABLE, workflow
from world_generation.prompts import create_character_diagram, create_faction, create_items, create_location_plan, create_npc, create_region, create_relationships, create_village
from world_generation.prompts.create_faction import FactionsStep
from world_generation.prompts.create_items import WorldItemsStep
from world_generation.prompts.create_npc import NPCStep
from world_generation.prompts.create_region import RegionStep
from world_generation.prompts.create_relationships import RelationshipsStep
from world_generation.prompts.create_village import PlacesStep
from world_generation.schemas import (
    CharacterSegmentDraft,
    CharacterDiagramStep,
    LocationPlanStep,
    RelationshipOpportunityDraft,
    WorldDraft,
    WorldItemDraft,
)
import world_generation.step_runtime as step_runtime
from world_generation.step_runtime import (
    MAX_STEP_ATTEMPTS,
    STEP_LABELS,
    AgentFrameworkChatAdapter as BaseAgentFrameworkChatAdapter,
    StepTranscript,
    StepUpdater,
    transcript_payloads,
)


PIPELINE_VERSION = "agent-framework-v1"


class AgentFrameworkChatAdapter(BaseAgentFrameworkChatAdapter):
    async def complete_json(
        self,
        *,
        model: ConfiguredModel,
        step_name: str,
        schema: type,
        messages: list[dict[str, str]],
    ) -> tuple[str, int]:
        return await chat_completion(
            model,
            messages,
            response_format=strict_json_schema(step_name, schema.model_json_schema()),
        )


step_runtime.CHAT_ADAPTER = AgentFrameworkChatAdapter()


@dataclass
class WorldGenerationState:
    prompt: str
    model: ConfiguredModel
    updater: Optional[StepUpdater] = None
    step_transcripts: list[StepTranscript] = field(default_factory=list)
    total_latency_ms: int = 0
    region_step: Optional[RegionStep] = None
    places_step: Optional[PlacesStep] = None
    factions_step: Optional[FactionsStep] = None
    location_plan_step: Optional[LocationPlanStep] = None
    character_diagram_step: Optional[CharacterDiagramStep] = None
    character_segments: list[CharacterSegmentDraft] = field(default_factory=list)
    relationship_opportunities: list[RelationshipOpportunityDraft] = field(default_factory=list)
    npc_step: Optional[NPCStep] = None
    relationships_step: Optional[RelationshipsStep] = None
    retry_step_name: Optional[str] = None
    cached_step_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class WorldItemsGenerationState:
    prompt: str
    model: ConfiguredModel
    world: WorldDraft
    scaffold: list[WorldItemDraft]
    updater: Optional[StepUpdater] = None
    initial_previous_error: Optional[str] = None
    initial_previous_response: Optional[str] = None
    step_transcripts: list[StepTranscript] = field(default_factory=list)
    total_latency_ms: int = 0
    world_items_step: Optional[WorldItemsStep] = None


def _final_output(run_result: Any) -> Any:
    if hasattr(run_result, "get_outputs"):
        outputs = run_result.get_outputs()
        if not outputs:
            raise ProviderError("Workflow produced no outputs.")
        return outputs[0]
    return run_result


@workflow(name="world_generation_pipeline")
async def world_generation_workflow(state: WorldGenerationState) -> WorldGenerationState:
    state = await create_region.run_step(state)
    state = await create_faction.run_step(state)
    state = await create_location_plan.run_step(state)
    state = await create_village.run_step(state)
    state = await create_character_diagram.run_step(state)
    state = await create_npc.run_step(state)
    state = await create_relationships.run_step(state)
    return state


@workflow(name="world_items_pipeline")
async def world_items_workflow(state: WorldItemsGenerationState) -> WorldItemsGenerationState:
    return await create_items.run_step(state)


async def build_world_draft(
    prompt: str,
    model: ConfiguredModel,
    updater: Optional[StepUpdater] = None,
) -> tuple[WorldDraft, str, int]:
    started = perf_counter()
    state = WorldGenerationState(prompt=prompt, model=model, updater=updater)
    run_result = await world_generation_workflow.run(state)
    final_state = _final_output(run_result)

    if (
        final_state.region_step is None
        or final_state.location_plan_step is None
        or final_state.places_step is None
        or final_state.factions_step is None
        or final_state.character_diagram_step is None
        or final_state.npc_step is None
        or final_state.relationships_step is None
    ):
        raise ProviderError("Workflow did not complete all world generation steps.")

    draft = WorldDraft(
        title=final_state.region_step.title,
        region=final_state.region_step.region,
        places=final_state.places_step.places,
        factions=final_state.factions_step.factions,
        npcs=final_state.npc_step.npcs,
        relationships=final_state.relationships_step.relationships,
    )
    latency_ms = int((perf_counter() - started) * 1000)
    raw_response = json.dumps(
        {
            "pipeline_version": PIPELINE_VERSION,
            "steps": transcript_payloads(final_state.step_transcripts),
            "location_plan": final_state.location_plan_step.model_dump(),
            "character_diagram": final_state.character_diagram_step.model_dump(),
            "character_segments": [segment.model_dump() for segment in final_state.character_segments],
            "relationship_opportunities": [opportunity.model_dump() for opportunity in final_state.relationship_opportunities],
            "final_world": draft.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )
    return draft, raw_response, latency_ms


def _decode_payload(value: Any) -> Optional[dict[str, Any]]:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _payload_by_step(job_steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for step in job_steps:
        payload = _decode_payload(step.get("parsed_payload"))
        if payload is not None and step.get("status") == "done":
            payloads[step["step_name"]] = payload
    return payloads


def _require_payload(payloads: dict[str, dict[str, Any]], step_name: str) -> dict[str, Any]:
    payload = payloads.get(step_name)
    if payload is None:
        raise ProviderError(
            f"Cannot resume this job because checkpoint '{step_name}' is missing. Use full restart instead."
        )
    return payload


def _state_from_checkpoints(
    *,
    prompt: str,
    model: ConfiguredModel,
    updater: Optional[StepUpdater],
    retry_step_name: str,
    payloads: dict[str, dict[str, Any]],
) -> WorldGenerationState:
    state = WorldGenerationState(
        prompt=prompt,
        model=model,
        updater=updater,
        retry_step_name=retry_step_name,
        cached_step_payloads=payloads,
    )
    state.region_step = RegionStep.model_validate(_require_payload(payloads, "region"))
    state.factions_step = FactionsStep.model_validate(_require_payload(payloads, "factions"))
    state.location_plan_step = LocationPlanStep.model_validate(_require_payload(payloads, "location_plan"))

    if retry_step_name.startswith("places_"):
        return state

    state.places_step = PlacesStep.model_validate(_require_payload(payloads, "villages_places"))
    diagram_payload = _require_payload(payloads, "character_diagram")
    state.character_diagram_step = CharacterDiagramStep.model_validate(diagram_payload)
    state.character_segments = [
        CharacterSegmentDraft.model_validate(segment)
        for segment in diagram_payload.get("character_segments", [])
    ]
    state.relationship_opportunities = [
        RelationshipOpportunityDraft.model_validate(opportunity)
        for opportunity in diagram_payload.get("relationship_opportunities", [])
    ]

    if retry_step_name.startswith("npcs_"):
        return state

    state.npc_step = NPCStep.model_validate(_require_payload(payloads, "npcs"))
    return state


def _final_world_from_state(final_state: WorldGenerationState) -> WorldDraft:
    if (
        final_state.region_step is None
        or final_state.places_step is None
        or final_state.factions_step is None
        or final_state.character_diagram_step is None
        or final_state.npc_step is None
        or final_state.relationships_step is None
    ):
        raise ProviderError("Workflow did not complete all world generation steps.")
    return WorldDraft(
        title=final_state.region_step.title,
        region=final_state.region_step.region,
        places=final_state.places_step.places,
        factions=final_state.factions_step.factions,
        npcs=final_state.npc_step.npcs,
        relationships=final_state.relationships_step.relationships,
    )


def _raw_response_from_state(final_state: WorldGenerationState, draft: WorldDraft) -> str:
    return json.dumps(
        {
            "pipeline_version": PIPELINE_VERSION,
            "steps": transcript_payloads(final_state.step_transcripts),
            "location_plan": final_state.location_plan_step.model_dump() if final_state.location_plan_step else None,
            "character_diagram": final_state.character_diagram_step.model_dump() if final_state.character_diagram_step else None,
            "character_segments": [segment.model_dump() for segment in final_state.character_segments],
            "relationship_opportunities": [opportunity.model_dump() for opportunity in final_state.relationship_opportunities],
            "final_world": draft.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )


async def build_world_draft_from_job_steps(
    prompt: str,
    model: ConfiguredModel,
    job_steps: list[dict[str, Any]],
    retry_step_name: str,
    updater: Optional[StepUpdater] = None,
) -> tuple[WorldDraft, str, int]:
    started = perf_counter()
    if not (
        retry_step_name.startswith("places_")
        or retry_step_name.startswith("npcs_")
        or retry_step_name.startswith("relationships_")
    ):
        raise ProviderError("Only place, NPC, and relationship batch steps can be resumed.")

    state = _state_from_checkpoints(
        prompt=prompt,
        model=model,
        updater=updater,
        retry_step_name=retry_step_name,
        payloads=_payload_by_step(job_steps),
    )

    if retry_step_name.startswith("places_"):
        state = await create_village.run_step(state)
        state = await create_character_diagram.run_step(state)
        state = await create_npc.run_step(state)
        state = await create_relationships.run_step(state)
    elif retry_step_name.startswith("npcs_"):
        state = await create_npc.run_step(state)
        state = await create_relationships.run_step(state)
    else:
        state = await create_relationships.run_step(state)

    draft = _final_world_from_state(state)
    latency_ms = int((perf_counter() - started) * 1000)
    return draft, _raw_response_from_state(state, draft), latency_ms


async def build_world_items_draft(
    prompt: str,
    model: ConfiguredModel,
    world: WorldDraft,
    scaffold: list[WorldItemDraft],
    previous_error: Optional[str] = None,
    previous_response: Optional[str] = None,
    updater: Optional[StepUpdater] = None,
) -> tuple[WorldItemsStep, str, int]:
    started = perf_counter()
    state = WorldItemsGenerationState(
        prompt=prompt,
        model=model,
        world=world,
        scaffold=scaffold,
        updater=updater,
        initial_previous_error=previous_error,
        initial_previous_response=previous_response,
    )
    run_result = await world_items_workflow.run(state)
    final_state = _final_output(run_result)
    if final_state.world_items_step is None:
        raise ProviderError("Workflow did not complete world item generation.")
    raw_response = json.dumps(
        {
            "pipeline_version": PIPELINE_VERSION,
            "steps": transcript_payloads(final_state.step_transcripts),
            "world_items": final_state.world_items_step.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )
    latency_ms = int((perf_counter() - started) * 1000)
    return final_state.world_items_step, raw_response, latency_ms
